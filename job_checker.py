import json
import os
import re
from datetime import datetime, timezone

from extract_job import extract_job
from job_checker_source import get_latest_jobs_source
from official_verifier import verify_job


SEEN_FILE = "seen_jobs.json"
JOBS_FOLDER = "jobs"


def load_seen_jobs():

    if not os.path.exists(SEEN_FILE):
        return set()

    try:

        with open(
            SEEN_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            return set(json.load(file))

    except Exception:

        return set()


def save_seen_jobs(seen_jobs):

    with open(
        SEEN_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            sorted(seen_jobs),
            file,
            indent=2,
            ensure_ascii=False
        )


def make_filename(title):

    filename = title.lower()

    filename = re.sub(
        r"[^a-z0-9]+",
        "-",
        filename
    )

    filename = filename.strip("-")

    if not filename:

        filename = "job"

    return filename[:100] + ".json"


def save_job(job):

    os.makedirs(
        JOBS_FOLDER,
        exist_ok=True
    )

    filename = make_filename(
        job.get("title", "job")
    )

    filepath = os.path.join(
        JOBS_FOLDER,
        filename
    )

    job["processed_at"] = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    with open(
        filepath,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            job,
            file,
            indent=2,
            ensure_ascii=False
        )

    return filepath


def main():

    print("=" * 60)
    print("SARKARI NAUKRI AUTOMATION")
    print("=" * 60)

    seen_jobs = load_seen_jobs()

    print(
        f"\nPreviously seen jobs: {len(seen_jobs)}"
    )

    print("\nChecking for new jobs...")

    jobs = get_latest_jobs_source()

    print(
        f"Found {len(jobs)} relevant links."
    )

    new_jobs = [
        job
        for job in jobs
        if job["url"] not in seen_jobs
    ]

    if not new_jobs:

        print("\nNo new jobs found.")
        print("\nFinished.")
        return

    print(
        f"\nNEW JOBS FOUND: {len(new_jobs)}"
    )

    successful_jobs = []

    for number, job in enumerate(
        new_jobs,
        start=1
    ):

        print("\n" + "=" * 60)

        print(
            f"PROCESSING JOB {number}/{len(new_jobs)}"
        )

        print("\nTitle:")
        print(job["title"])

        print("\nURL:")
        print(job["url"])

        try:

            print("\nExtracting job details...")

            data = extract_job(
                job["url"]
            )

            print("\nVerifying official source...")
            verification = verify_job(data)
            data["verification"] = verification

            print("Verification status:")
            print(verification["verification_status"])

            filepath = save_job(data)

            print("\nSUCCESS")
            print(f"Saved: {filepath}")

            successful_jobs.append(
                job["url"]
            )

        except Exception as error:

            print("\nERROR:")
            print(str(error))

            print(
                "\nThis job will be retried next time."
            )

    seen_jobs.update(
        successful_jobs
    )

    save_seen_jobs(
        seen_jobs
    )

    print("\n" + "=" * 60)
    print("AUTOMATION FINISHED")
    print("=" * 60)


if __name__ == "__main__":
    main()
