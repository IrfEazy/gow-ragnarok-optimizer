"""Scraping dati armature e armi dalla wiki IGN + caricamento CSV."""

import logging
import os
import re
import time
from io import StringIO
from os import fspath
from typing import Any

import pandas as pd
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

STAT_COLS = ["Strength", "Defense", "Runic", "Vitality", "Cooldown", "Luck"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
BASE_URL = "https://www.ign.com"
PIECE_NAMES = ["Chest", "Wrist", "Waist"]


# ─── Funzioni di parsing ────────────────────────────────────


def parse_stats_text(cell) -> dict[Any, int]:
    text = cell.get_text(separator="\n")
    pairs = re.findall(r"([A-Za-z][A-Za-z ]*?)\s*:\s*([\d,]+)", text)
    return {k.strip(): int(v.replace(",", "")) for k, v in pairs}


def parse_detail_table(table_tag) -> list[Any]:
    rows = table_tag.find_all("tr")
    records = []
    current_levels = []
    i = 0
    while i < len(rows):
        cells = rows[i].find_all(["th", "td"])
        cell_texts = [c.get_text(strip=True) for c in cells]

        level_positions = [
            (col_idx, t)
            for col_idx, t in enumerate(cell_texts)
            if re.match(r"^Level\s+[\d.]+$", t)
        ]
        if level_positions:
            current_levels = level_positions
            i += 1
            continue

        if not current_levels or all(t == "" for t in cell_texts):
            i += 1
            continue

        full_text = " ".join(cell_texts)
        if "Strength:" in full_text or "Defense:" in full_text:
            for col_idx, level_name in current_levels:
                if col_idx < len(cells):
                    stats = parse_stats_text(cells[col_idx])
                    if stats:
                        record = {"Level": level_name.replace("Level ", "")}
                        record.update(stats)
                        records.append(record)
            i += 1
            continue

        if "Hacksilver:" in full_text or "Upgrade" in full_text:
            for col_idx, level_name in current_levels:
                if col_idx < len(cells):
                    costs = parse_stats_text(cells[col_idx])
                    level_val = level_name.replace("Level ", "")
                    for rec in records:
                        if (
                            rec["Level"] == level_val
                            and "Upgrade_Hacksilver" not in rec
                        ):
                            for k, v in costs.items():
                                rec[f"Upgrade_{k}"] = v
                            break
            i += 1
            continue

        i += 1
    return records


def scrape_armor_detail(armor_url) -> dict[Any, Any]:
    resp = requests.get(armor_url, headers=HEADERS)
    resp.raise_for_status()
    s = BeautifulSoup(resp.text, "lxml")
    tables = s.find_all("table")
    pieces = {}
    for idx, tbl in enumerate(tables):
        if idx >= 3:
            break
        piece_name = PIECE_NAMES[idx]
        prev_header = tbl.find_previous(["h2", "h3", "h4"])
        section = prev_header.get_text(strip=True) if prev_header else ""
        level_records = parse_detail_table(tbl)
        if level_records:
            piece_df = pd.DataFrame(level_records)
            piece_df.attrs["section_title"] = section
            pieces[piece_name] = piece_df
    return pieces


# ─── Caricamento / Scraping ─────────────────────────────────


def load_csvs(armor_csv, weapons_csv) -> tuple[Any, Any]:
    """Load armor and weapon DataFrames from CSV files.

    Raises FileNotFoundError if either CSV is missing.
    """
    armor_csv = fspath(armor_csv)
    weapons_csv = fspath(weapons_csv)

    if not os.path.exists(armor_csv):
        raise FileNotFoundError(
            f"Armor CSV not found: {armor_csv}\n"
            "Run 'python -m gow_optimizer.scraper' to generate it."
        )
    if not os.path.exists(weapons_csv):
        raise FileNotFoundError(
            f"Weapons CSV not found: {weapons_csv}\n"
            "Run 'python -m gow_optimizer.scraper' to generate it."
        )

    all_pieces_df = pd.read_csv(armor_csv)
    all_weapons_df = pd.read_csv(weapons_csv)
    return all_pieces_df, all_weapons_df


def scrape_and_save(armor_csv, weapons_csv) -> Any:
    """Scrape armor and weapon data from IGN wiki and save to CSV files."""
    armor_csv = fspath(armor_csv)
    weapons_csv = fspath(weapons_csv)

    # ─── Scraping completo ───
    logger.info("=== SCRAPING DAL WEB ===")

    # 1. Armature
    logger.info("Scaricamento pagina armature...")
    response = requests.get(
        f"{BASE_URL}/wikis/god-of-war-ragnarok/All_Armor_Sets", headers=HEADERS
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")
    all_tables = soup.find_all("table")

    dfs = []
    for tbl in all_tables:
        try:
            t = pd.read_html(StringIO(str(tbl)))[0]
            dfs.append(t)
        except Exception:
            pass
    df = max(dfs, key=lambda x: x.shape[0])

    target_table = all_tables[1]
    rows = target_table.find_all("tr")[1:]
    armor_data = []
    for row in rows:
        cells = row.find_all(["td", "th"])
        if cells:
            link_tag = cells[0].find("a")
            name = (
                link_tag.get_text(strip=True)
                if link_tag
                else cells[0].get_text(strip=True)
            )
            href = None
            if link_tag and link_tag.get("href"):
                href = link_tag["href"]
                if not href.startswith("http"):
                    href = BASE_URL + href
            armor_data.append({"Set Name": name, "URL": href})

    df_links = pd.DataFrame(armor_data)
    df["Set Name"] = df_links["Set Name"]
    df["URL"] = df_links["URL"]
    logger.info("  Set trovati: %d, con link: %d", len(df), df["URL"].notna().sum())

    armor_details = {}
    errors = []
    valid_sets = df[df["URL"].notna()]
    total = len(valid_sets)
    for i, (_, row) in enumerate(valid_sets.iterrows()):
        name = row["Set Name"]
        url = row["URL"]
        logger.info("  [%d/%d] %s...", i + 1, total, name)
        try:
            pieces = scrape_armor_detail(url)
            armor_details[name] = pieces
            logger.info("    OK (%d pezzi)", len(pieces))
        except Exception as e:
            errors.append((name, str(e)))
            logger.error("    ERRORE: %s", e)
        time.sleep(0.5)
    logger.info(
        "  Completato: %d/%d OK, %d errori", len(armor_details), total, len(errors)
    )

    records = []
    for set_name, pieces in armor_details.items():
        for piece_type, piece_df in pieces.items():
            section_title = piece_df.attrs.get("section_title", "")
            for _, row_data in piece_df.iterrows():
                record = {
                    "Set Name": set_name,
                    "Piece Type": piece_type,
                    "Piece Name": section_title,
                }
                for col in piece_df.columns:
                    record[col] = row_data[col]
                records.append(record)
    all_pieces_df = pd.DataFrame(records)
    all_pieces_df["Level"] = pd.to_numeric(all_pieces_df["Level"], errors="coerce")
    all_pieces_df["Total Stats"] = all_pieces_df[STAT_COLS].sum(axis=1)
    logger.info(
        "  all_pieces_df: %d righe, %d pezzi",
        all_pieces_df.shape[0],
        all_pieces_df["Piece Name"].nunique(),
    )

    # 2. Armi
    logger.info("Scaricamento pagina armi...")
    resp_weapons = requests.get(
        f"{BASE_URL}/wikis/god-of-war-ragnarok/All_Weapon_and_Shield_Attachments",
        headers=HEADERS,
    )
    resp_weapons.raise_for_status()
    soup_weapons = BeautifulSoup(resp_weapons.text, "lxml")
    weapon_tables = soup_weapons.find_all("table")

    weapon_categories = {
        1: "Leviathan Axe",
        2: "Blades of Chaos",
        3: "Draupnir Spear",
        4: "Shield",
    }
    weapon_data = []
    for tbl_idx, category in weapon_categories.items():
        tbl_tag = weapon_tables[tbl_idx]
        tbl_rows = tbl_tag.find_all("tr")[1:]
        for row in tbl_rows:
            cells = row.find_all(["td", "th"])
            if cells:
                link_tag = cells[0].find("a")
                name = (
                    link_tag.get_text(strip=True)
                    if link_tag
                    else cells[0].get_text(strip=True)
                )
                href = None
                if link_tag and link_tag.get("href"):
                    href = link_tag["href"]
                    if not href.startswith("http"):
                        href = BASE_URL + href
                weapon_data.append({"Category": category, "Name": name, "URL": href})
    weapons_df = pd.DataFrame(weapon_data)
    logger.info("  Attachment trovati: %d", len(weapons_df))

    weapon_details = {}
    weapon_errors = []
    total_w = len(weapons_df)
    for i, (_, row) in enumerate(weapons_df.iterrows()):
        name = row["Name"]
        cat = row["Category"]
        url = row["URL"]
        logger.info("  [%d/%d] %s — %s...", i + 1, total_w, cat, name)
        try:
            resp_w = requests.get(url, headers=HEADERS)
            resp_w.raise_for_status()
            soup_w = BeautifulSoup(resp_w.text, "lxml")
            tbls = soup_w.find_all("table")
            if tbls:
                records_w = parse_detail_table(tbls[0])
                if records_w:
                    wdf = pd.DataFrame(records_w)
                    wdf["Level"] = pd.to_numeric(wdf["Level"], errors="coerce")
                    weapon_details[(cat, name)] = wdf
                    logger.info("    OK (%d livelli)", len(records_w))
                else:
                    logger.info("    VUOTO")
            else:
                logger.info("    VUOTO")
        except Exception as e:
            weapon_errors.append((name, str(e)))
            logger.error("    ERRORE: %s", e)
        time.sleep(0.5)
    logger.info(
        "  Completato: %d/%d OK, %d errori",
        len(weapon_details),
        total_w,
        len(weapon_errors),
    )

    weapon_records = []
    for (category, weapon_name), wdf in weapon_details.items():
        for _, row_data in wdf.iterrows():
            record = {"Category": category, "Weapon Name": weapon_name}
            for col in wdf.columns:
                record[col] = row_data[col]
            weapon_records.append(record)
    all_weapons_df = pd.DataFrame(weapon_records)
    all_weapons_df["Level"] = pd.to_numeric(all_weapons_df["Level"], errors="coerce")
    for c in STAT_COLS:
        if c not in all_weapons_df.columns:
            all_weapons_df[c] = 0
    all_weapons_df[STAT_COLS] = all_weapons_df[STAT_COLS].fillna(0)

    # Fix: Soldier's Sauroter Level 9.1
    fix_mask = (all_weapons_df["Weapon Name"] == "Soldier's Sauroter") & (
        all_weapons_df["Level"] == 9.1
    )
    all_weapons_df.loc[fix_mask, "Cooldown"] = 19
    all_weapons_df.loc[fix_mask, "Luck"] = 19
    all_weapons_df["Total Stats"] = all_weapons_df[STAT_COLS].sum(axis=1)
    logger.info(
        "  all_weapons_df: %d righe, %d armi",
        all_weapons_df.shape[0],
        all_weapons_df["Weapon Name"].nunique(),
    )

    # 3. Salvataggio CSV
    all_pieces_df.to_csv(armor_csv, index=False)
    all_weapons_df.to_csv(weapons_csv, index=False)
    logger.info("CSV salvati: %s, %s", armor_csv, weapons_csv)

    return all_pieces_df, all_weapons_df


if __name__ == "__main__":
    from gow_optimizer.paths import DATA_DIR

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger = logging.getLogger(__name__)

    armor_csv = DATA_DIR / "all_pieces.csv"
    weapons_csv = DATA_DIR / "all_weapons.csv"

    logger.info("Starting scraper...")
    scrape_and_save(armor_csv, weapons_csv)
    logger.info("Done! CSVs are ready.")
