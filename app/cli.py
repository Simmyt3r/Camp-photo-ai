"""
Command-line interface (section 34).

    python -m app.cli register --id P001 --name "John Doe" --photos a.jpg --photos b.jpg
    python -m app.cli process --input ./photos --output ./sorted
    python -m app.cli review-queue
    python -m app.cli review-confirm 14
    python -m app.cli rebuild-cache
    python -m app.cli report --format json

`evaluate` and `benchmark` are stubbed here -- they belong to the
accuracy and performance-testing framework (sections 21-23), which is a
separate phase of this build (see README.md "What's next").
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import click
import cv2
import numpy as np

from app.bootstrap import AppContext
from app.database.db import get_session
from app.database.models import Participant, ProcessingRun, ReferenceEmbedding
from app.services.face_embedding import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL_NAME, EMBEDDING_MODEL_VERSION
from app.services.image_processing import encode_thumbnail_jpeg
from app.services.review_service import confirm_match, list_pending_reviews, reassign_match, reject_match
from app.utilities.file_utils import file_sha256
from app.workers.batch_processor import run_batch

logger = logging.getLogger("camp_photo_ai.cli")


def _bootstrap() -> AppContext:
    """Thin wrapper kept so every command below reads `_bootstrap()` --
    the actual settings/hardware/model-provider logic lives in
    app.bootstrap.AppContext, shared with the GUI (app/main.py)."""
    return AppContext.bootstrap()


@click.group()
def cli():
    """CampPhoto AI -- AI-assisted camp photography sorting."""


@cli.command()
@click.option("--id", "participant_id", required=True, help="Unique participant ID")
@click.option("--name", "full_name", required=True, help="Participant full name")
@click.option("--reg-number", default=None, help="Optional registration number")
@click.option("--category", default=None, help="Optional category/group/platoon")
@click.option("--photos", multiple=True, required=True, type=click.Path(exists=True),
              help="One or more reference photographs (repeat the flag for each)")
def register(participant_id, full_name, reg_number, category, photos):
    """Register a participant and generate reference embeddings."""
    context = _bootstrap()
    embedding_service = context.embedding_service

    accepted, rejected = [], []
    for photo_str in photos:
        photo_path = Path(photo_str)
        image = cv2.imread(str(photo_path))
        if image is None:
            rejected.append((photo_path, "could not be read"))
            continue
        faces = embedding_service.embed_image(image)
        if len(faces) == 0:
            rejected.append((photo_path, "no face detected"))
            continue
        if len(faces) > 1:
            rejected.append((photo_path, f"{len(faces)} faces detected -- expected exactly 1"))
            continue
        embedding, _det_score, _bbox = faces[0]
        accepted.append((photo_path, embedding, image))

    for path, reason in rejected:
        click.echo(f"  x {path.name}: {reason}")

    if not accepted:
        click.echo("No usable reference photographs -- registration aborted.")
        sys.exit(1)

    with get_session() as session:
        existing = session.query(Participant).filter_by(participant_id=participant_id).one_or_none()
        if existing:
            click.echo(f"Participant ID '{participant_id}' already exists.")
            sys.exit(1)

        participant = Participant(
            participant_id=participant_id,
            full_name=full_name,
            registration_number=reg_number,
            category=category,
            consent_given=True,
        )
        session.add(participant)
        session.flush()

        for path, vector, image in accepted:
            session.add(ReferenceEmbedding(
                participant_db_id=participant.id,
                vector=vector.astype(np.float32).tobytes(),
                dimensions=EMBEDDING_DIMENSIONS,
                model_name=EMBEDDING_MODEL_NAME,
                model_version=EMBEDDING_MODEL_VERSION,
                source_image_hash=file_sha256(path),
                thumbnail=encode_thumbnail_jpeg(image),
            ))

    click.echo(f"Registered {full_name} ({participant_id}) with {len(accepted)} reference embedding(s).")
    if len(accepted) < 3:
        click.echo("  Tip: 3-5 reference photos from different angles/lighting is recommended.")


@cli.command()
@click.option("--input", "input_dir", required=True, type=click.Path(exists=True, file_okay=False))
@click.option("--output", "output_dir", required=True, type=click.Path(file_okay=False))
@click.option("--no-resume", is_flag=True, help="Ignore the cache and reprocess every photo")
def process(input_dir, output_dir, no_resume):
    """Scan a folder of photographs and sort them into participant folders."""
    context = _bootstrap()
    settings = context.settings
    click.echo(f"Processing mode: {context.mode.upper()} ({context.provider})")

    click.echo("Warming up face-analysis model...")
    context.embedding_service.warm_up()

    def on_progress(stats, filename):
        click.echo(
            f"\r[{stats.processed}/{stats.total_photos}] {stats.images_per_second:.1f} img/s | "
            f"auto={stats.auto_matched} review={stats.review} unmatched={stats.unmatched} "
            f"errors={stats.errors} | {filename[:40]}",
            nl=False,
        )

    with get_session() as session:
        stats = run_batch(
            session, settings, Path(input_dir), Path(output_dir),
            context.embedding_service, progress_callback=on_progress, resume=not no_resume,
        )
    click.echo()
    click.echo(
        f"Done. {stats.processed} photos, {stats.faces_detected} faces, "
        f"{stats.auto_matched} auto-matched, {stats.review} sent to review, "
        f"{stats.unmatched} unmatched, {stats.errors} errors "
        f"in {stats.elapsed_seconds:.1f}s ({stats.images_per_second:.1f} img/s)."
    )


@cli.command(name="rebuild-cache")
def rebuild_cache():
    """Clear the processing cache so the next `process` run reprocesses everything."""
    _bootstrap()
    from app.database.models import ProcessingCache
    with get_session() as session:
        count = session.query(ProcessingCache).delete()
    click.echo(f"Cleared {count} cached entries.")


@cli.command(name="review-queue")
@click.option("--limit", default=20)
def review_queue(limit):
    """List photographs waiting in the human-review queue (section 14)."""
    _bootstrap()
    with get_session() as session:
        pending = list_pending_reviews(session, limit=limit)
        if not pending:
            click.echo("Review queue is empty.")
            return
        for record in pending:
            second = ""
            if record.second_best_participant_id:
                second = f" (2nd: {record.second_best_participant_id} @ {record.second_best_score:.3f})"
            click.echo(
                f"[{record.id}] {Path(record.file_path).name} face#{record.face_index} "
                f"best={record.best_candidate_participant_id}@{record.best_score:.3f}{second} "
                f"margin={record.score_margin:.3f} -- {record.reason}"
            )


@cli.command(name="review-confirm")
@click.argument("match_id", type=int)
@click.option("--participant-db-id", type=int, default=None,
              help="Reassign to this participant's internal DB id instead of the suggested match")
@click.option("--reviewer", default="cli-operator")
def review_confirm(match_id, participant_db_id, reviewer):
    """Confirm (or reassign-and-confirm) a review-queue match. Copies the
    photo into the participant's folder."""
    context = _bootstrap()
    settings = context.settings
    out_dir = Path(settings.output_dir)
    with get_session() as session:
        if participant_db_id is not None:
            reassign_match(session, match_id, participant_db_id, reviewer,
                            output_dir=out_dir, duplicate_policy=settings.duplicate_policy)
        else:
            confirm_match(session, match_id, reviewer,
                           output_dir=out_dir, duplicate_policy=settings.duplicate_policy)
    click.echo(f"Match {match_id} confirmed.")


@cli.command(name="review-reject")
@click.argument("match_id", type=int)
@click.option("--reviewer", default="cli-operator")
def review_reject(match_id, reviewer):
    """Reject a review-queue match."""
    _bootstrap()
    with get_session() as session:
        reject_match(session, match_id, reviewer)
    click.echo(f"Match {match_id} rejected.")


@cli.command()
@click.option("--run-id", type=int, default=None, help="Processing run ID (defaults to the most recent)")
@click.option("--format", "fmt", type=click.Choice(["json", "csv"]), default="json")
@click.option("--output", "output_path", type=click.Path(), default=None)
def report(run_id, fmt, output_path):
    """Export a processing report for a past run (section 20)."""
    from app.services.reporting import build_report

    _bootstrap()
    with get_session() as session:
        run = session.get(ProcessingRun, run_id) if run_id is not None else (
            session.query(ProcessingRun).order_by(ProcessingRun.id.desc()).first()
        )
        if run is None:
            click.echo("No processing runs found yet -- run `process` first.")
            sys.exit(1)

        report_obj = build_report(run)
        run_id_for_name = run.id

    dest = Path(output_path) if output_path else Path(f"report_run{run_id_for_name}.{fmt}")
    report_obj.to_json(dest) if fmt == "json" else report_obj.to_csv(dest)
    click.echo(f"Report written to {dest}")


@cli.command()
@click.option("--dataset", type=click.Path(exists=True, file_okay=False), required=True,
              help="Directory of person_id/photo.jpg subfolders, optionally with an _unknown/ folder. See docs/ACCURACY.md.")
@click.option("--gallery-size", default=3, show_default=True,
              help="Photos per identity to use as the reference gallery; the rest become probes.")
@click.option("--thresholds", default=None,
              help="Comma-separated auto-match threshold grid, e.g. 0.5,0.55,0.6,0.65,0.7,0.75 (default: spec section 22's example grid)")
@click.option("--review-gap", default=0.15, show_default=True,
              help="review_threshold = auto_threshold - review_gap for each grid point")
@click.option("--min-precision", default=0.98, show_default=True,
              help="Minimum precision the recommended threshold must clear")
@click.option("--output-dir", type=click.Path(), default="accuracy_report", show_default=True)
def evaluate(dataset, gallery_size, thresholds, review_gap, min_precision, output_dir):
    """Accuracy evaluation + threshold calibration against a labelled
    validation dataset (sections 21-22). See docs/ACCURACY.md."""
    from app.services.evaluation import (
        format_sweep_table, load_validation_dataset, plot_threshold_sweep,
        recognition_accuracy, recommend_threshold, sweep_thresholds,
    )

    context = _bootstrap()
    settings = context.settings
    out_dir = Path(output_dir)

    click.echo(f"Loading dataset from {dataset} (embedding every usable photo -- this can take a while)...")
    loaded = load_validation_dataset(Path(dataset), context.embedding_service, gallery_size=gallery_size)

    click.echo(
        f"Loaded {len(loaded.gallery)} identities, {loaded.known_probe_count} known probes, "
        f"{loaded.impostor_probe_count} impostor probes."
    )
    if loaded.skipped:
        click.echo(f"Skipped {len(loaded.skipped)} item(s):")
        for name, reason in loaded.skipped:
            click.echo(f"  x {name}: {reason}")

    if not loaded.gallery:
        click.echo("No usable identities loaded -- nothing to evaluate. See docs/ACCURACY.md for the expected layout.")
        sys.exit(1)
    if not loaded.probes:
        click.echo("No usable probes loaded (every identity needs 2+ usable photos) -- nothing to evaluate.")
        sys.exit(1)

    acc = recognition_accuracy(loaded.gallery, loaded.probes, match_strategy=settings.match_strategy, top_k=settings.top_k)
    click.echo("\nRecognition accuracy (threshold-independent -- is the right identity even the top candidate?):")
    for n, value in acc.items():
        click.echo(f"  Top-{n}: {value:.1%}")
    if len(loaded.gallery) < 5:
        click.echo("  (Top-5 is close to meaningless with only "
                    f"{len(loaded.gallery)} registered identities -- it saturates trivially.)")

    grid = tuple(float(t.strip()) for t in thresholds.split(",")) if thresholds else None
    sweep_kwargs = dict(
        review_gap=review_gap, minimum_score_margin=settings.minimum_score_margin,
        match_strategy=settings.match_strategy, top_k=settings.top_k,
    )
    results = sweep_thresholds(loaded.gallery, loaded.probes, threshold_grid=grid, **sweep_kwargs) if grid else \
        sweep_thresholds(loaded.gallery, loaded.probes, **sweep_kwargs)

    click.echo(f"\nThreshold sweep (review_threshold = auto_threshold - {review_gap}, "
               f"minimum_score_margin={settings.minimum_score_margin}, strategy={settings.match_strategy}):\n")
    click.echo(format_sweep_table(results))

    recommended = recommend_threshold(results, min_precision=min_precision)
    click.echo("")
    if recommended:
        click.echo(
            f"Suggested starting point: auto_match_threshold={recommended.auto_match_threshold:.2f} "
            f"(precision={recommended.precision:.3f}, recall={recommended.recall:.3f}) -- "
            f"the highest-recall option that still clears {min_precision:.0%} precision on THIS dataset. "
            f"Not a universal answer (section 22) -- re-run this against your own data before trusting it."
        )
    else:
        click.echo(
            f"No threshold in the sweep reached {min_precision:.0%} precision on this dataset -- "
            f"widen --thresholds, add more/better reference photos, or lower --min-precision to see the trade-offs."
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    table_path = out_dir / "threshold_sweep.txt"
    table_path.write_text(format_sweep_table(results) + "\n")
    try:
        plot_path = out_dir / "threshold_sweep.png"
        plot_threshold_sweep(results, plot_path)
        click.echo(f"\nWrote {table_path} and {plot_path}")
    except ImportError:
        click.echo(f"\nWrote {table_path}. Install matplotlib to also get {out_dir / 'threshold_sweep.png'}.")


@cli.command()
@click.option("--target", type=click.Choice(["matching", "database", "pipeline", "all"]), default="all",
              help="Which layer to benchmark. 'pipeline' requires --photos.")
@click.option("--sizes", default=None,
              help="Comma-separated scale values for matching (registered participants) and database "
                   "(rows) -- both synthetic, safe at any size. Defaults to spec section 24's targets: "
                   "1000,10000 for matching, 1000,10000,50000 for database.")
@click.option("--photos", type=click.Path(exists=True, file_okay=False), default=None,
              help="Folder of real photos for --target pipeline (cycled through if fewer than the requested size).")
@click.option("--pipeline-sizes", default="20,100", show_default=True,
              help="Image counts for the REAL pipeline benchmark -- deliberately separate from --sizes "
                   "and small by default, since these run actual face detection/embedding, not synthetic "
                   "data. Raise this deliberately, not via --sizes, and expect it to take a while on CPU.")
@click.option("--extrapolate-to", default=None,
              help="Comma-separated additional pipeline sizes to project via linear extrapolation "
                   "(clearly labelled, not measured) -- e.g. 1000,5000,10000.")
@click.option("--output-dir", type=click.Path(), default="performance_report", show_default=True)
def benchmark(target, sizes, photos, pipeline_sizes, extrapolate_to, output_dir):
    """Performance and load testing (sections 23-24). See docs/PERFORMANCE.md."""
    from app.services.benchmarking import (
        benchmark_database, benchmark_matching, benchmark_pipeline, extrapolate_linear,
        format_benchmark_table, measure_model_load_time, plot_benchmark_results,
    )

    context = _bootstrap()
    settings = context.settings
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    all_results = []

    def _parse_sizes(raw, default):
        return tuple(int(s.strip()) for s in raw.split(",")) if raw else default

    if target in ("matching", "all"):
        n = _parse_sizes(sizes, (1_000, 10_000))
        click.echo(f"Benchmarking matching at n={list(n)} registered participants (synthetic embeddings)...")
        results = benchmark_matching(list(n), match_strategy=settings.match_strategy, top_k=settings.top_k)
        all_results.extend(results)
        click.echo(format_benchmark_table(results))
        click.echo("")

    if target in ("database", "all"):
        n = _parse_sizes(sizes, (1_000, 10_000, 50_000))
        click.echo(f"Benchmarking database at n={list(n)} rows (disposable temp DB, never your real data)...")
        results = benchmark_database(list(n), out_dir / "_benchmark_scratch.db")
        all_results.extend(results)
        click.echo(format_benchmark_table(results))
        click.echo("")

    if target in ("pipeline", "all"):
        if not photos:
            if target == "pipeline":
                click.echo("--target pipeline requires --photos <folder of real images>.")
                sys.exit(1)
            click.echo("Skipping pipeline benchmark (no --photos given). Real inference speed has no "
                       "synthetic substitute -- run with --target pipeline --photos <folder> separately.")
        else:
            photo_paths = [p for p in Path(photos).iterdir() if p.is_file()]
            if not photo_paths:
                click.echo(f"No files found in {photos}.")
                sys.exit(1)
            n_values = _parse_sizes(pipeline_sizes, (20, 100))
            click.echo("Warming up face-analysis model...")
            model_load_ms = measure_model_load_time(context.embedding_service)
            click.echo(f"Model load / first-inference time: {model_load_ms:.0f}ms")

            for n in n_values:
                click.echo(f"Benchmarking pipeline at n={n} real images (from {len(photo_paths)} source photo(s), "
                            f"cycled if fewer than n)...")
                result = benchmark_pipeline(photo_paths, n, context.embedding_service,
                                             max_dimension=settings.max_image_dimension)
                all_results.append(result)
                click.echo(format_benchmark_table([result]))

                if extrapolate_to:
                    for target_n in (int(s.strip()) for s in extrapolate_to.split(",")):
                        projected = extrapolate_linear(result, target_n)
                        all_results.append(projected)
                click.echo("")

            if extrapolate_to:
                click.echo(format_benchmark_table([r for r in all_results if r.name == "pipeline" and r.extrapolated]))
                click.echo(
                    "\nExtrapolated rows assume linear scaling from the measured n above -- real "
                    "throughput at that scale depends on the actual deployment hardware (CPU cores, "
                    "GPU, disk speed) and should be measured directly there, not just projected."
                )

    if all_results:
        table_path = out_dir / "benchmark_results.txt"
        table_path.write_text(format_benchmark_table(all_results) + "\n")
        try:
            plot_path = out_dir / "benchmark_results.png"
            plot_benchmark_results(all_results, plot_path)
            click.echo(f"\nWrote {table_path} and {plot_path}")
        except ImportError:
            click.echo(f"\nWrote {table_path}. Install matplotlib to also get {out_dir / 'benchmark_results.png'}.")


if __name__ == "__main__":
    cli()
