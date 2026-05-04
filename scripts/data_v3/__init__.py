"""Data v3 pipeline — clean, normalize, dedup four source spreadsheets
into the canonical slim contact CSVs that the system imports.

Stages (each is a separate module so they can be invoked or tested
independently):

    extract    — read raw rows out of the Excel source files
    normalize  — clean strings, emails, phones, countries, names
    dedup      — collapse within-file duplicates + enforce cross-file
                 priority (existing > lapsed > carpet > yarn)
    build      — CLI that orchestrates extract → normalize → dedup and
                 writes Data/Data_v3/*.csv plus _build_report.md

The canonical record shape lives in `schema.ContactV3`.
"""
