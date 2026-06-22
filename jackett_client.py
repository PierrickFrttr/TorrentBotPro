import requests
from config import JACKETT_URL, JACKETT_API_KEY


def _format_size(size_bytes):
    if size_bytes > 1024 ** 3:
        return f"{size_bytes / (1024 ** 3):.2f} GB"
    return f"{size_bytes / (1024 ** 2):.2f} MB"


_FRENCH_TAGS = ("FRENCH", "TRUEFRENCH", "VFF", "VF", "VOSTFR", "MULTI")


def search(query, timeout=15):
    """Interroge Jackett et retourne les résultats triés par seeders."""
    q = query.strip()
    if not any(t in q.upper() for t in _FRENCH_TAGS):
        q = f"{q} FRENCH"
    url = f"{JACKETT_URL}/api/v2.0/indexers/all/results"
    params = {"apikey": JACKETT_API_KEY, "Query": q}
    try:
        response = requests.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.ConnectionError:
        raise ConnectionError(f"Jackett ne répond pas sur {JACKETT_URL}. Vérifiez qu'il est lancé.")
    except Exception as e:
        raise RuntimeError(f"Erreur Jackett : {e}")

    results = []
    for item in data.get("Results", []):
        results.append({
            "title":    item.get("Title") or "Sans titre",
            "seeders":  item.get("Seeders", 0),
            "size":     _format_size(item.get("Size", 0)),
            "size_bytes": item.get("Size", 0),
            "magnet":   item.get("MagnetUri") or item.get("Link"),
            "indexer":  item.get("IndexerName") or "Inconnu",
            "category": item.get("CategoryDesc") or "Inconnu",
            "_raw":     item,
        })

    results.sort(key=lambda x: x["seeders"], reverse=True)
    return results
