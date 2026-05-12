"""
core/train.py — Generate face embeddings for all registered students

Reads every image in dataset/<reg_number>/, passes each through InsightFace,
averages the embeddings per student, and saves everything to encodings/encodings.pkl.

Run after registering new students:
    python core/train.py

Run with --student to re-encode a single student:
    python core/train.py --student G1F22UBSCS173
"""

import pickle
import logging
import argparse
import sys
import time
import numpy as np
import cv2
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATASET_DIR, ENCODINGS_FILE
from core.face_engine import get_engine
from db.connection import db_session
from db.models import Student

logger = logging.getLogger(__name__)


# ─── Encoding data structure saved to pkl ────────────────────────────────────
# {
#   "G1F22UBSCS173": {
#       "name":       "Fahad Gujjar",
#       "embedding":  np.array shape (512,),   # mean of all valid embeddings
#       "image_count": 28,                      # how many images contributed
#   },
#   ...
# }


def encode_student(reg_number: str, student_dir: Path, engine) -> dict | None:
    """
    Encode all face images for one student.

    Args:
        reg_number:  Student reg number (used as key).
        student_dir: Path to folder containing .jpg images.
        engine:      Loaded InsightFace FaceAnalysis instance.

    Returns:
        Dict with name, embedding, image_count — or None if no faces found.
    """
    images = sorted(student_dir.glob("*.jpg")) + sorted(student_dir.glob("*.png"))

    if not images:
        logger.warning(f"No images found in {student_dir}")
        return None

    # get student name from DB
    with db_session() as session:
        student = session.query(Student).filter_by(reg_number=reg_number).first()
        name    = student.name if student else reg_number

    embeddings = []
    failed     = 0

    for img_path in images:
        frame = cv2.imread(str(img_path))
        if frame is None:
            logger.warning(f"Could not read image: {img_path}")
            failed += 1
            continue

        faces = engine.get(frame)
        if not faces:
            logger.debug(f"No face in: {img_path.name}")
            failed += 1
            continue

        # use the largest face in the image
        face = max(faces, key=lambda f: (
            (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1])
        ))
        embeddings.append(face.normed_embedding)

    if not embeddings:
        logger.error(f"No valid face embeddings for {reg_number} — all {len(images)} images failed.")
        return None

    # average all embeddings and re-normalise
    mean_embedding = np.mean(embeddings, axis=0)
    mean_embedding = mean_embedding / np.linalg.norm(mean_embedding)

    success_rate = len(embeddings) / len(images) * 100
    logger.info(
        f"  {reg_number} | {name:<25} | "
        f"{len(embeddings)}/{len(images)} images ({success_rate:.0f}%) | "
        f"embedding shape: {mean_embedding.shape}"
    )

    return {
        "name":        name,
        "embedding":   mean_embedding,
        "image_count": len(embeddings),
    }


def train(target_reg: str = None) -> dict:
    """
    Main training function.

    Args:
        target_reg: If given, only re-encode this one student.
                    If None, encode all students in dataset/.

    Returns:
        Full encodings dict (including previously saved encodings if updating one student).
    """
    logger.info("=" * 60)
    logger.info("Training started — generating face embeddings")
    logger.info("=" * 60)

    # load existing encodings (if any) — needed when updating a single student
    existing_encodings = {}
    if ENCODINGS_FILE.exists():
        with open(ENCODINGS_FILE, "rb") as f:
            existing_encodings = pickle.load(f)
        logger.info(f"Loaded {len(existing_encodings)} existing encodings from {ENCODINGS_FILE}")

    # load InsightFace model (will take ~5s on first call)
    print("\nLoading InsightFace model (this takes ~5 seconds on first run)...")
    t0     = time.time()
    engine = get_engine()
    print(f"Model loaded in {time.time() - t0:.1f}s\n")

    # determine which students to encode
    if target_reg:
        student_dirs = [DATASET_DIR / target_reg]
        if not student_dirs[0].exists():
            logger.error(f"Dataset folder not found: {student_dirs[0]}")
            sys.exit(1)
    else:
        student_dirs = [d for d in DATASET_DIR.iterdir() if d.is_dir()]

    if not student_dirs:
        logger.error(f"No student folders found in {DATASET_DIR}")
        print(f"\nNo students registered yet. Run:  python core/register.py\n")
        sys.exit(1)

    logger.info(f"Encoding {len(student_dirs)} student(s)...")
    print(f"{'Reg Number':<22} {'Name':<25} {'Images Used':<15} {'Status'}")
    print("-" * 75)

    new_encodings = dict(existing_encodings)   # start with existing, overwrite updated
    success_count = 0
    fail_count    = 0

    for student_dir in sorted(student_dirs):
        reg_number = student_dir.name
        result     = encode_student(reg_number, student_dir, engine)

        if result:
            new_encodings[reg_number] = result
            success_count += 1
            print(
                f"{reg_number:<22} {result['name']:<25} "
                f"{result['image_count']:<15} ✓ Done"
            )
            # update is_encoded flag in DB
            with db_session() as session:
                student = session.query(Student).filter_by(reg_number=reg_number).first()
                if student:
                    student.is_encoded = True
        else:
            fail_count += 1
            print(f"{reg_number:<22} {'???':<25} {'0':<15} ✗ Failed (no faces detected)")

    # save to encodings.pkl
    ENCODINGS_FILE.parent.mkdir(exist_ok=True)
    with open(ENCODINGS_FILE, "wb") as f:
        pickle.dump(new_encodings, f, protocol=pickle.HIGHEST_PROTOCOL)

    print("\n" + "=" * 75)
    print(f"Training complete!")
    print(f"  Students encoded:  {success_count}")
    print(f"  Students failed:   {fail_count}")
    print(f"  Encodings saved:   {ENCODINGS_FILE}")
    print(f"  Total in database: {len(new_encodings)}")
    print(f"\nNext step: run  python core/recognize.py  to start live recognition.\n")

    logger.info(f"Training done — {success_count} encoded, {fail_count} failed.")
    return new_encodings


def load_encodings() -> dict:
    """
    Load encodings from disk. Called by recognize.py at startup.

    Returns:
        Dict of {reg_number: {name, embedding, image_count}}
        Empty dict if file not found.
    """
    if not ENCODINGS_FILE.exists():
        logger.warning(f"Encodings file not found: {ENCODINGS_FILE}")
        logger.warning("Run:  python core/train.py  to generate encodings.")
        return {}

    with open(ENCODINGS_FILE, "rb") as f:
        encodings = pickle.load(f)

    logger.info(f"Loaded {len(encodings)} encodings from {ENCODINGS_FILE}")
    return encodings


# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate face encodings for registered students.")
    parser.add_argument(
        "--student",
        type=str,
        default=None,
        metavar="REG_NUMBER",
        help="Re-encode a single student by registration number (re-encodes all if omitted).",
    )
    args = parser.parse_args()
    train(target_reg=args.student)
