#!/usr/bin/env python3
"""
generate_subtitle_contact_sheets.py

Uses ImageMagick's `montage` tool to generate contact sheet pages from
the subtitle proof images in /media/daveg/Lib/Movies/subtitle_proof (or /media/daveg/Lib/.subtitle_proof),
and combines all generated pages into a single multi-page PDF.

Layout:
  - 3x3 grid (9 proof images / 3 movies per page)
  - 540px width per thumbnail to ensure subtitles remain clear and legible
  - Clean movie title printed below each image
  - Multiprocessed for high-speed batch generation
  - Automatically combines all contact sheets into one comprehensive PDF
"""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time

DEFAULT_INPUT_DIR = "/media/daveg/Lib/Movies/subtitle_proof"
DEFAULT_OUTPUT_DIR = "/media/daveg/Lib/Movies/contact_sheets"
DEFAULT_PDF_NAME = "subtitle_proof_contact_sheets.pdf"


def parse_args():
    parser = argparse.ArgumentParser(description="Generate contact sheets and combined PDF for subtitle proof images.")
    parser.add_argument(
        "--input-dir", "-i",
        default=DEFAULT_INPUT_DIR,
        help="Path to directory containing subtitle proof jpg images."
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=DEFAULT_OUTPUT_DIR,
        help="Path to directory where contact sheet images will be saved."
    )
    parser.add_argument(
        "--grid", "-g",
        default="3x3",
        help="Grid layout per contact sheet page (default: 3x3)."
    )
    parser.add_argument(
        "--thumb-width", "-w",
        default=540,
        type=int,
        help="Thumbnail width in pixels (default: 540)."
    )
    parser.add_argument(
        "--max-workers", "-j",
        default=os.cpu_count() or 4,
        type=int,
        help="Number of parallel worker processes (default: CPU count)."
    )
    parser.add_argument(
        "--pdf-name",
        default=DEFAULT_PDF_NAME,
        help="Filename for the combined PDF (default: subtitle_proof_contact_sheets.pdf)."
    )
    parser.add_argument(
        "--no-pdf",
        action="store_true",
        help="Skip combining contact sheets into a single PDF."
    )
    return parser.parse_args()


def render_page(args_tuple):
    page_num, total_pages, img_list, output_dir, grid, thumb_width = args_tuple
    out_file = os.path.join(output_dir, f"contact_sheet_{page_num:03d}.jpg")
    cmd = ["montage"]

    for f in img_list:
        base = os.path.basename(f)
        m = re.match(r"^(.*?)_proof_(\d+.*)\.jpg$", base, re.IGNORECASE)
        movie_title = m.group(1) if m else os.path.splitext(base)[0]
        wrapped_title = "\n".join(textwrap.wrap(movie_title, width=32))
        cmd.extend(["-label", wrapped_title, f])

    cmd.extend([
        "-tile", grid,
        "-geometry", f"{thumb_width}x+12+12",
        "-pointsize", "15",
        "-font", "DejaVu-Sans-Bold",
        "-background", "#181818",
        "-fill", "#e0e0e0",
        "-quality", "90",
        out_file
    ])

    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return page_num, out_file


def combine_to_pdf(page_files, output_pdf_path, chunk_size=50):
    """
    Combines a list of image files into a single PDF document.
    Converts chunks of images to temporary PDFs, then unites them using pdfunite (or ghostscript/convert).
    """
    print(f"\nCombining {len(page_files)} contact sheet pages into single PDF: {output_pdf_path}...")
    t_start = time.time()

    temp_dir = tempfile.mkdtemp(prefix="contact_sheet_pdf_")
    chunk_pdfs = []

    try:
        total_chunks = (len(page_files) + chunk_size - 1) // chunk_size
        for idx in range(0, len(page_files), chunk_size):
            chunk = page_files[idx:idx + chunk_size]
            chunk_num = (idx // chunk_size) + 1
            chunk_pdf = os.path.join(temp_dir, f"chunk_{chunk_num:03d}.pdf")
            chunk_pdfs.append(chunk_pdf)

            cmd = ["convert"] + chunk + [chunk_pdf]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

            if chunk_num % 5 == 0 or chunk_num == total_chunks:
                pct = (chunk_num / total_chunks) * 100
                print(f"  [PDF Chunk {chunk_num}/{total_chunks}] ({pct:.1f}%) Processed {len(chunk)} pages")

        # Merge chunk PDFs using pdfunite or gs
        has_pdfunite = shutil.which("pdfunite") is not None
        if has_pdfunite:
            unite_cmd = ["pdfunite"] + chunk_pdfs + [output_pdf_path]
            subprocess.run(unite_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        else:
            gs_cmd = [
                "gs", "-dBATCH", "-dNOPAUSE", "-q",
                "-sDEVICE=pdfwrite", f"-sOutputFile={output_pdf_path}"
            ] + chunk_pdfs
            subprocess.run(gs_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

        elapsed = time.time() - t_start
        size_mb = os.path.getsize(output_pdf_path) / (1024 * 1024)
        print(f"[✓] Successfully generated combined PDF: {output_pdf_path} ({size_mb:.1f} MB, {elapsed:.2f}s)")
        return True
    except Exception as e:
        print(f"[-] Failed to combine into PDF: {e}", file=sys.stderr)
        return False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def main():
    args = parse_args()
    input_dir = os.path.realpath(args.input_dir)
    output_dir = os.path.realpath(args.output_dir)

    if not os.path.isdir(input_dir):
        fallback = "/media/daveg/Lib/.subtitle_proof"
        if os.path.isdir(fallback):
            input_dir = os.path.realpath(fallback)
        else:
            print(f"Error: Input directory not found: {input_dir}", file=sys.stderr)
            sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    # Sort files naturally so all proof snapshots for a movie stay grouped together
    files = sorted(glob.glob(os.path.join(input_dir, "*.jpg")))
    if not files:
        print(f"No JPG proof images found in {input_dir}", file=sys.stderr)
        sys.exit(1)

    cols, rows = map(int, args.grid.lower().split("x"))
    batch_size = cols * rows
    batches = [files[i:i + batch_size] for i in range(0, len(files), batch_size)]
    total_pages = len(batches)

    print(f"Found {len(files)} proof images in {input_dir}")
    print(f"Generating {total_pages} contact sheet pages ({args.grid} grid, {args.thumb_width}px width) into {output_dir}...")

    t0 = time.time()
    tasks = [
        (idx + 1, total_pages, batch, output_dir, args.grid, args.thumb_width)
        for idx, batch in enumerate(batches)
    ]

    completed = 0
    generated_pages = {}
    with ProcessPoolExecutor(max_workers=args.max_workers) as executor:
        futures = {executor.submit(render_page, t): t[0] for t in tasks}
        for fut in as_completed(futures):
            p_num, out_path = fut.result()
            generated_pages[p_num] = out_path
            completed += 1
            if completed % 25 == 0 or completed == total_pages:
                pct = (completed / total_pages) * 100
                print(f"  [{completed}/{total_pages}] ({pct:.1f}%) Generated {os.path.basename(out_path)}")

    elapsed = time.time() - t0
    print(f"\nDone generating contact sheets! {total_pages} pages in {elapsed:.2f}s ({total_pages / elapsed:.1f} pages/sec).")
    print(f"Images saved to: {output_dir}")

    # Combine into single PDF unless disabled
    if not args.no_pdf:
        # Determine output PDF path
        if os.path.isabs(args.pdf_name):
            pdf_path = args.pdf_name
        else:
            parent_dir = os.path.dirname(output_dir)
            pdf_path = os.path.join(parent_dir, args.pdf_name)

        ordered_pages = [generated_pages[i] for i in sorted(generated_pages.keys())]
        combine_to_pdf(ordered_pages, pdf_path)


if __name__ == "__main__":
    main()
