@echo off
:: update code
git pull
:: run script
uv run entry_points/main.py
:: pause