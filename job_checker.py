import json
import os
import re
from datetime import datetime, timezone

from extract_job import extract_job
from job_checker_source import get_latest_jobs_source
from official_verifier import verify_job
from update_detector import detect_update


SEEN_FILE = "seen_jobs.json"
JOBS_FOLDER = "jobs"


def load_seen_jobs():
    if not os.path.exists(SEEN_FILE):
        return set()

    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as file:
            return set(json.load(file))
    except Exception:
        return set()


def save_seen_jobs(seen_jobs):
    with open(SEEN_FILE, "w", encoding="utf-8") as file:
        json.dump(
            sorted(seen_jobs),
            file,
            indent=2,
            ensure_ascii=False
        )


def make_filename(title):
    filename = title.lower()
    filename = re.sub(r"[^a-z0-9]+", "-", filename)
    filename = filename.strip("-")

    if not filename:
        filename = "job"

    return filename[:100] + ".json"


def load_saved_jobs():
    saved = {}

    if not os.path.isdir(JOBS_FOLDER):
        return saved

    for filename in os.listdir(JOBS_FOLDER):
        if not filename.endswith(".json"):
            continue

        filepath = os.path.join(JOBS_FOLDER, filename)

        try:
            with open(filepath, "r", encoding="utf-8") as file:
                data = json.load(file)

            source_url = data.get("source_url")
            if source_url:
                saved[source_url] = {
                    "data": data,
                    "filepath": filepath
                }
        except Exception:
            continue

    return saved


def save_job(job, existing_filepath=None):
    os.makedirs(JOBS_FOLDER, exist_ok=True)

    filepath = existing_filepath

    if not filepath:
        filename = make_filename(job.get("title", "job"))
        filepath = os.path.join(JOBS_FOLDER, filename)

    job["processed_at"] = datetime.now(timezone.utc).isoformat()

    with open(filepath, "w", encoding="utf-8") as file:
        json.dump(
            job,
            file,
            indent=2,
            ensure_ascii=False
        )

    return filepath


def add_change_history(job, update):
    history = job.get("change_history", [])

    history.append({
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "change_type": update["change_type"],
        "changes": update["changes"]
    })

    # Keep the file compact while preserving recent history.
    job["change_history"] = history[-20:]
    job["last_update"] = update


def process_new_job(job):
    print("\nNEW JOB")
    print(job["title"])

    data = extract_job(job["url"])

    print("Verifying official source...")
    data["verification"] = verify_job(data)

    filepath = save_job(data)

    print(
        "Saved:",
        filepath,
        "| Verification:",
        data["verification"]["verification_status"]
    )

    return True


def process_existing_job(job, saved):
    old_data = saved["data"]

    print("\nCHECKING EXISTING JOB")
    print(job["title"])

    current = extract_job(job["url"])
    update = detect_update(old_data, current)

    if not update["has_material_update"]:
        print("No material update.")
        return True

    print(
        "MATERIAL UPDATE:",
        update["change_type"]
    )

    for change in update["changes"]:
        print(
            f"- {change['label']}: "
            f"{change['old']} -> {change['new']}"
        )

    print("Verifying updated job against official source...")
    current["verification"] = verify_job(current)

    # Preserve the previous version so important changes are auditable.
    current["previous_version"] = old_data
    add_change_history(current, update)

    filepath = save_job(
        current,
        existing_filepath=saved["filepath"]
    )

    print(
        "Updated:",
        filepath,
        "| Verification:",
        current["verification"]["verification_status"]
    )

    print("ALERT READY:", update["change_type"])

    return True


def main():
    print("=" * 60)
    print("SARKARI NAUKRI AUTOMATION")
    print("=" * 60)

    seen_jobs = load_seen_jobs()
    saved_jobs = load_saved_jobs()

    print(f"Previously seen URLs: {len(seen_jobs)}")
    print(f"Saved recruitments: {len(saved_jobs)}")

    print("\nChecking latest SarkariResult listings...")

    jobs = get_latest_jobs_source()

    print(f"Found {len(jobs)} relevant links.")

    if not jobs:
        print("\nNo listings returned by source.")
        return

    successful_jobs = []
    new_count = 0
    update_count = 0
    unchanged_count = 0
    error_count = 0

    for number, job in enumerate(jobs, start=1):
        print("\n" + "=" * 60)
        print(f"PROCESSING {number}/{len(jobs)}")
        print("Title:", job["title"])
        print("URL:", job["url"])

        try:
            if job["url"] not in saved_jobs:
                process_new_job(job)
                new_count += 1
            else:
                before_history = len(
                    saved_jobs[job["url"]]["data"].get(
                        "change_history",
                        []
                    )
                )

                process_existing_job(
                    job,
                    saved_jobs[job["url"]]
                )

                # Reload the file to determine whether history changed.
                refreshed = load_saved_jobs().get(job["url"])
                after_history = (
                    len(refreshed["data"].get("change_history", []))
                    if refreshed
                    else before_history
                )

                if after_history > before_history:
                    update_count += 1
                else:
                    unchanged_count += 1

            successful_jobs.append(job["url"])

        except Exception as error:
            error_count += 1

            print("\nERROR:")
            print(str(error))

            print("This listing will be retried next time.")

    seen_jobs.update(successful_jobs)
    save_seen_jobs(seen_jobs)

    print("\n" + "=" * 60)
    print("AUTOMATION FINISHED")
    print("=" * 60)
    print("New jobs:", new_count)
    print("Material updates:", update_count)
    print("Unchanged:", unchanged_count)
    print("Errors:", error_count)


if __name__ == "__main__":
    main()
