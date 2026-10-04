# Grip

A dry-rock forecast for the sea cliffs of north-east Scotland, updated hourly by GitHub Actions and published with GitHub Pages.

- `crags.json`: crags, walls, aspects, weather zones and the direction each stretch of coast faces. Edit this to add or change crags.
- `grip.py`: fetches Open-Meteo forecasts, models the state of the rock hour by hour and builds the page.
- `observations.csv`: how conditions actually felt on logged days, used to check the model.
- `.github/workflows/update.yml`: runs every hour.

Daily push: add a repository secret called `NTFY_TOPIC` with your ntfy topic name. The message goes out on the 08:00 run.

Forecast data from Open-Meteo (CC BY 4.0), including UK Met Office data (CC BY-SA 4.0).
