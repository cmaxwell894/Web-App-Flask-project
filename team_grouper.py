# file: team_grouper.py
import pandas as pd
import re
import os

def clean_club_name(name, abbreviation_map):
    for abbr, full in abbreviation_map.items():
        name = re.sub(abbr, full, name, flags=re.IGNORECASE)
    name = re.sub(r'\bF\.?C\.?\b', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\bAFC\b', '', name, flags=re.IGNORECASE)
    name = re.sub(r'[.,]$', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name

def process_excel(input_file, output_file):
    # All your processing logic here, but:
    #  - remove GUI log updates
    #  - write to output_file
    # return output_file at the end
    df = pd.read_excel(input_file)

    # Example simple version
    df['Name'] = df['Name'].astype(str).str.strip()
    df = df.drop_duplicates(subset=['Name'])
    df.to_excel(output_file, index=False)

    return output_file
