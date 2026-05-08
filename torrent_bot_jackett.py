import requests
import argparse
import sys

# --- CONFIGURATION ---
JACKETT_URL = "http://127.0.0.1:9117"
API_KEY = "puqye2oamnc81mr8mqrvfe605adq8wbi"
# ---------------------

def search_jackett(query):
    url = f"{JACKETT_URL}/api/v2.0/indexers/all/results"
    params = {
        'apikey': API_KEY,
        'Query': query,
    }
    
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get('Results', []):
            # Calcul de la taille en GB ou MB pour l'affichage
            size_bytes = item.get('Size', 0)
            if size_bytes > 1024**3:
                size_str = f"{size_bytes / (1024**3):.2f} GB"
            else:
                size_str = f"{size_bytes / (1024**2):.2f} MB"

            results.append({
                'title': item.get('Title'),
                'seeders': item.get('Seeders', 0),
                'size': size_str,
                'link': item.get('MagnetUri') or item.get('Guid') or item.get('Link'),
                'indexer': item.get('IndexerName')
            })
        return results
    except Exception as e:
        print(f"Erreur de connexion à Jackett : {e}")
        print("Assure-toi que Jackett est bien lancé sur http://127.0.0.1:9117")
        return []

def main():
    parser = argparse.ArgumentParser(description="Bot de recherche Torrent via Jackett")
    parser.add_argument("query", help="Le film, série ou logiciel à chercher")
    args = parser.parse_args()
    
    print(f"Recherche globale (VF/Multi) pour : '{args.query}'...")
    results = search_jackett(args.query)
    
    # Tri par nombre de seeds (les plus sains en premier)
    results.sort(key=lambda x: x['seeders'], reverse=True)

    if not results:
        print("\nAucun résultat trouvé.")
        print("Conseils :")
        print("1. Vérifie que Jackett est lancé (JackettConsole.exe).")
        print("2. Vérifie que tu as ajouté des 'Indexers' (ex: Torrent9, LimeTorrents) dans l'interface Jackett.")
        return

    print(f"\n{'#' :<3} | {'Indexer':<15} | {'Titre':<60} | {'S':<5} | {'Taille':<10}")
    print("-" * 105)
    
    for i, res in enumerate(results[:20], 1):
        title_trunc = (res['title'][:57] + '..') if len(res['title']) > 57 else res['title']
        print(f"{i:<3} | {res['indexer']:<15} | {title_trunc:<60} | {res['seeders']:<5} | {res['size']:<10}")

    while True:
        choice = input("\nEntrez un numéro pour obtenir le lien (ou 'q' pour quitter) : ")
        if choice.lower() == 'q':
            break
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(results):
                target = results[idx]
                print(f"\n--- DÉTAILS DU TORRENT ---")
                print(f"Titre   : {target['title']}")
                print(f"Indexer : {target['indexer']}")
                print(f"Lien    : {target['link']}")
                print(f"--------------------------")
                print("\nCopie le lien ci-dessus dans ton logiciel de téléchargement (qBittorrent, etc.).")
            else:
                print("Numéro invalide.")
        except ValueError:
            print("Veuillez entrer un nombre valide.")

if __name__ == "__main__":
    main()
