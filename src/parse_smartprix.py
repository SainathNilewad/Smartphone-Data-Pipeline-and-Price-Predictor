
import sys
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
from bs4 import BeautifulSoup

BASE_URL = "https://www.smartprix.com"
RAW_DIR = Path("data/raw")
OUT_DIR = Path("data/processed")


def clean_text(text):
    """Normalize whitespace and unusual spaces."""
    return " ".join(
        text.replace("\u2009", " ")
        .replace("\xa0", " ")
        .split()
    )


def classify_spec(line):
    """Classify a specification by its content."""
    low = line.lower()

    if "memory card" in low:
        return "card"
    if "sim" in low:
        return "sim"
    if "battery" in low or "mah" in low:
        return "battery"
    if "ram" in low or "inbuilt" in low:
        return "ram"
    if "inch" in low or " px" in low:
        return "display"
    if "camera" in low or " mp" in low:
        return "camera"
    if "processor" in low or "ghz" in low or "core" in low:
        return "processor"
    if "android" in low or "ios" in low:
        return "os"

    return None


def parse_card(card):
    name_el = card.select_one("h2")
    link_el = card.select_one("a.name[href]")
    price_el = card.select_one("span.price")
    score_el = card.select_one("div.score b")

    row = {
        "model": clean_text(name_el.get_text(" ", strip=True))
        if name_el else None,
        "url": None,
        "price": clean_text(price_el.get_text(" ", strip=True))
        if price_el else None,
        "spec_score": clean_text(score_el.get_text(" ", strip=True))
        if score_el else None,
        "sim": None,
        "processor": None,
        "ram": None,
        "battery": None,
        "display": None,
        "camera": None,
        "card": None,
        "os": None,
        "unclassified": None,
    }

    if link_el:
        row["url"] = urljoin(BASE_URL, link_el["href"])

    leftovers = []

    for li in card.select("ul.sm-feat.specs li"):
        line = clean_text(li.get_text(" ", strip=True))

        if not line:
            continue

        key = classify_spec(line)

        if key and row[key] is None:
            row[key] = line
        else:
            leftovers.append(line)

    row["unclassified"] = " | ".join(leftovers) or None
    return row


def parse_html(html):
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("div.sm-product.has-features")

    records = [parse_card(card) for card in cards]
    df = pd.DataFrame(records)

    if not df.empty:
        # Remove duplicate products by URL where available.
        df["_dedupe_key"] = df["url"]

        # Use the model name as a fallback when URL is missing.
        missing_url = df["_dedupe_key"].isna()
        df.loc[missing_url, "_dedupe_key"] = (
            df.loc[missing_url, "model"]
        )

        df = df.drop_duplicates(
            subset=["_dedupe_key"],
            keep="first",
        ).drop(columns=["_dedupe_key"])

    return df


def get_html_path():
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        if not path.is_file():
            raise FileNotFoundError(f"HTML file not found: {path}")
        return path

    # Explicitly exclude the checkpoint file.
    candidates = [
        path for path in RAW_DIR.glob("smartprix_*.html")
        if path.name != "smartprix_checkpoint.html"
    ]

    if not candidates:
        raise FileNotFoundError(
            f"No timestamped Smartprix HTML files found in {RAW_DIR}"
        )

    return max(candidates, key=lambda path: path.stat().st_mtime)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    html_path = get_html_path()
    print(f"Reading: {html_path}")

    html = html_path.read_text(encoding="utf-8")
    df = parse_html(html)

    timestamp = html_path.stem.replace("smartprix_", "")
    output_path = OUT_DIR / f"smartprix_phones_{timestamp}.csv"

    df.to_csv(output_path, index=False, encoding="utf-8-sig")

    print(f"Parsed unique phone cards: {len(df)}")
    print(f"CSV saved to: {output_path}")

    if not df.empty:
        print("\nMissing values by column:")
        print(df.isna().sum())


if __name__ == "__main__":
    main()
