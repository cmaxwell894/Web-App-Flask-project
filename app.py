from flask import Flask, request, render_template, send_file
import pandas as pd
import re
import os
import tempfile
import json


app = Flask(__name__)


with open("keywords.json", "r") as f:
    keywords_data = json.load(f)


youth_keywords = keywords_data["youth_keywords"]
mens_keywords = keywords_data["mens_keywords"]
ladies_keywords = keywords_data["ladies_keywords"]
color_keywords = keywords_data["color_keywords"]
disability_keywords = keywords_data["disability_keywords"]
abbreviation_map = keywords_data["abbreviation_map"]
club_suffixes = keywords_data["club_suffixes"]

all_keywords = set(youth_keywords + mens_keywords + ladies_keywords + color_keywords + disability_keywords)
# =========================
# Clean club names (for internal normalization only)
# =========================
def clean_club_name(name, abbreviation_map):
    for abbr, full in abbreviation_map.items():
        name = re.sub(abbr, full, name, flags=re.IGNORECASE)
    # Keep FC for display, only remove for internal normalization
    name_norm = re.sub(r'\bF\.?C\.?\b', '', name, flags=re.IGNORECASE)
    name_norm = re.sub(r'\bAFC\b', '', name_norm, flags=re.IGNORECASE)
    name_norm = re.sub(r'[.,]$', '', name_norm)
    name_norm = re.sub(r'\s+', ' ', name_norm).strip()
    return name_norm

# =========================
# Extract base club name
# =========================
def get_base_club_name(team_name, age_pattern, youth_keywords, all_keywords, club_suffixes):
    dash_parts = [p.strip() for p in team_name.split('-')]
    base_part = dash_parts[0]

    words = base_part.split()
    base_name_parts = []

    for word in words:
        if age_pattern.search(word) or word in youth_keywords or word in all_keywords:
            break
        base_name_parts.append(word)

    if words and words[-1] in club_suffixes and words[-1] not in base_name_parts:
        base_name_parts.append(words[-1])

    if not base_name_parts:
        base_name_parts = words[:1]

    return " ".join(base_name_parts).strip()

# =========================
# Normalize club names for merging (internal only)
# =========================
def normalize_club_name_for_merge(club_name):
    club_name = club_name.upper()
    club_name = club_name.replace('.', '')
    club_name = re.sub(r'\(.*?\)', '', club_name)
    club_name = re.sub(r'\s+', ' ', club_name).strip()
    club_name = re.sub(r'\b(JF?C?|F C|F C)\b', 'FC', club_name)
    return club_name

# =========================
# Second-pass merge of youth teams
# =========================
def merge_youth_subteams(grouped_teams):
    merged_grouped = {}
    for key, teams in grouped_teams.items():
        club, category = key.rsplit('(', 1)
        category = category.rstrip(')').strip()
        club = club.strip()

        if category.lower() == "youth":
            base_club = normalize_club_name_for_merge(club)
        else:
            base_club = club

        merged_key = f"{base_club} ({category})"
        merged_grouped.setdefault(merged_key, []).extend(teams)

    merged_grouped = {k: sorted(v) for k, v in merged_grouped.items()}
    return merged_grouped

# =========================
# Process file
# =========================
def process_file(file_storage):
    tmpdir = tempfile.mkdtemp()
    input_path = os.path.join(tmpdir, file_storage.filename)
    file_storage.save(input_path)

    xls = pd.ExcelFile(input_path)
    for sheet_name in xls.sheet_names:
        temp_df = pd.read_excel(xls, sheet_name=sheet_name)
        if "Name" in temp_df.columns:
            df = temp_df
            break
    else:
        raise Exception("No sheet with a 'Name' column found")

    df["Name"] = df["Name"].fillna("").astype(str)

    # Remove scoreline rows
    scoreline_pattern = re.compile(r'^\d+\s*-\s*\d+(\s*\(.*?\))?$', re.IGNORECASE)
    df = df[~df["Name"].str.match(scoreline_pattern)].reset_index(drop=True)

    # Handle duplicates
    duplicates = df[df.duplicated(subset=["Name"], keep=False)].copy()
    duplicate_counts = duplicates.groupby("Name").size().reset_index(name="Occurrences")
    duplicate_counts["Duplicate_Count"] = duplicate_counts["Occurrences"] - 1
    total_duplicates = duplicate_counts["Duplicate_Count"].sum()
    df = df.drop_duplicates(subset=["Name"]).reset_index(drop=True)

    grouped_teams = {}
    original_team_count = len(df) + total_duplicates
    age_pattern = re.compile(r'\bU\d+', re.IGNORECASE)

    for team in df["Name"]:
        if not team.strip():
            continue

        original_team = team
        team_cleaned = clean_club_name(team, abbreviation_map)

        # Determine category
        if age_pattern.search(team_cleaned) or re.search(r'\b(?:' + '|'.join(youth_keywords) + r')\b', team_cleaned):
            category = "Youth"
            club_name = get_base_club_name(team_cleaned, age_pattern, youth_keywords, all_keywords, club_suffixes)
        else:
            if re.search(r'\b(?:' + '|'.join(ladies_keywords) + r')\b', team_cleaned, flags=re.IGNORECASE):
                category = "Ladies"
            elif re.search(r'\b(?:' + '|'.join(mens_keywords) + r')\b', team_cleaned, flags=re.IGNORECASE):
                category = "Mens"
            elif re.search(r'\b(?:' + '|'.join(disability_keywords) + r')\b', team_cleaned, flags=re.IGNORECASE):
                category = "Disability"
            else:
                category = "Mens"
            club_name = get_base_club_name(team_cleaned, age_pattern, all_keywords, all_keywords, club_suffixes)

        # Preserve FC prefix if present
        fc_prefix = ''
        fc_match = re.match(r'^(F\.?C\.?)\s+', original_team)
        if fc_match:
            fc_prefix = fc_match.group(1) + ' '

        display_club_name = f"{fc_prefix}{club_name}"

        # --- Use normalized club name as key for merging ---
        norm_club_name = normalize_club_name_for_merge(display_club_name)
        key = f"{norm_club_name} ({category})"
        grouped_teams.setdefault(key, []).append(original_team)

    # Second-pass merge for youth sub-teams
    grouped_teams = merge_youth_subteams(grouped_teams)

    # Convert to DataFrame
    grouped_list = [[k, len(v), ", ".join(v)] for k, v in sorted(grouped_teams.items())]
    grouped_df = pd.DataFrame(grouped_list, columns=["Club (Category)", "Team Count", "Teams"])

    # Totals & checks
    grouped_total = grouped_df["Team Count"].sum()
    total_row = pd.DataFrame([["TOTAL", grouped_total, ""]], columns=grouped_df.columns)
    grouped_df = pd.concat([grouped_df, total_row], ignore_index=True)
    check_total = grouped_total + total_duplicates
    blank_row = pd.DataFrame([["", "", ""]], columns=grouped_df.columns)
    check_row = pd.DataFrame(
        [["CHECK (Grouped + Duplicates)", f"{grouped_total} + {total_duplicates} = {check_total}", f"Original = {original_team_count}"]],
        columns=grouped_df.columns,
    )
    grouped_df = pd.concat([grouped_df, blank_row, check_row], ignore_index=True)

    # Save output
    output_file = os.path.join(tmpdir, "grouped_output.xlsx")
    with pd.ExcelWriter(output_file) as writer:
        grouped_df.to_excel(writer, sheet_name="Grouped Teams", index=False)
        if total_duplicates > 0:
            duplicate_counts.to_excel(writer, sheet_name="Exact Duplicates", index=False)
            dup_summary = pd.DataFrame([["TOTAL DUPLICATES", total_duplicates, ""]],
                                       columns=["Name", "Occurrences", "Duplicate_Count"])
            dup_summary.to_excel(writer, sheet_name="Exact Duplicates", index=False, startrow=len(duplicate_counts)+2)

    return output_file

# =========================
# Flask routes
# =========================
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        if "file" not in request.files:
            return "No file uploaded", 400
        file = request.files["file"]
        if file.filename == "":
            return "No file selected", 400

        output_path = process_file(file)
        return send_file(output_path, as_attachment=True, download_name="grouped_output.xlsx")

    return render_template("index.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Use Railway PORT or default to 5000
    app.run(host="0.0.0.0", port=port, debug=True)

