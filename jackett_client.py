import re
import unicodedata
import requests
from config import JACKETT_URL, JACKETT_API_KEY

_FRENCH_TAGS = ("FRENCH", "TRUEFRENCH", "VFF", "VF", "VOSTFR", "MULTI")


def _format_size(size_bytes):
    if size_bytes > 1024 ** 3:
        return f"{size_bytes / (1024 ** 3):.2f} GB"
    return f"{size_bytes / (1024 ** 2):.2f} MB"


def _normalize(query):
    """Remove accents, clean spacing."""
    nfd     = unicodedata.normalize("NFD", query)
    no_acc  = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    return " ".join(no_acc.split())


def _strip_year(query):
    return re.sub(r"\s*\b(19|20)\d{2}\b\s*", " ", query).strip()


def _with_french(q):
    if not any(t in q.upper() for t in _FRENCH_TAGS):
        return f"{q} FRENCH"
    return q


def _raw_search(q, timeout):
    """Single Jackett query — no retry logic."""
    url    = f"{JACKETT_URL}/api/v2.0/indexers/all/results"
    params = {"apikey": JACKETT_API_KEY, "Query": _with_french(q)}
    resp   = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    results = []
    for item in resp.json().get("Results", []):
        results.append({
            "title":      item.get("Title") or "Sans titre",
            "seeders":    item.get("Seeders", 0),
            "size":       _format_size(item.get("Size", 0)),
            "size_bytes": item.get("Size", 0),
            "magnet":     item.get("MagnetUri") or item.get("Link"),
            "indexer":    item.get("IndexerName") or "Inconnu",
            "category":   item.get("CategoryDesc") or "Inconnu",
            "_raw":       item,
        })
    results.sort(key=lambda x: x["seeders"], reverse=True)
    return results


def search(query, timeout=60, fallback_title=None):
    """
    Cascade search — stops at first strategy that returns results.
      1. Query normalisee (accents supprimes)
      2. Sans annee  (si la requete en contient une)
      3. fallback_title (titre original TMDB, passe par torrent_gui)
    Retourne (results, label) — label indique quelle strategie a fonctionne.
    Leve ConnectionError / TimeoutError sur echec reseau.
    """
    base    = _normalize(query.strip())
    no_year = _strip_year(base)

    strategies = [("exacte", base)]
    if no_year and no_year != base:
        strategies.append(("sans annee", no_year))
    if fallback_title:
        fb = _normalize(fallback_title.strip())
        if fb.lower() not in {base.lower(), no_year.lower()}:
            strategies.append(("titre original", fb))

    last_exc = None
    for label, q in strategies:
        if not q:
            continue
        try:
            results = _raw_search(q, timeout)
            if results:
                return results, label
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError(
                f"Jackett ne repond pas sur {JACKETT_URL}."
            ) from e
        except requests.exceptions.ReadTimeout as e:
            raise TimeoutError(
                f"Jackett n a pas repondu en {timeout}s — trop d indexeurs actifs ?"
            ) from e
        except Exception as e:
            last_exc = e

    if last_exc:
        raise RuntimeError(f"Erreur Jackett : {last_exc}")
    return [], "aucun resultat"
