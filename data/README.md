# Scientific Dataset Management

This directory documents the scientific datasets
used by Lunar Landing Site Navigator.

## Planned Datasets

- NASA SPICE ephemeris kernels
- Lunar Digital Elevation Models
- Lunar imagery
- Lunar coordinate reference datasets

## Local Data Directories

The following directories are excluded from Git:

- data/raw/
- data/processed/
- data/cache/
- data/kernels/
- data/dem/
- data/imagery/

## Reproducibility Requirements

Each dataset must eventually document:

1. Dataset name
2. Source institution
3. Official download URL
4. Version or release date
5. Coordinate reference system
6. Units
7. Spatial resolution
8. File checksum
9. Processing methodology

## Security

Do not commit API credentials or confidential files.

## Version Control

Large scientific datasets should be downloaded
independently rather than stored in normal Git history.