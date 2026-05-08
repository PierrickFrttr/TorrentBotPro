import requests
from bs4 import BeautifulSoup
import argparse
import sys

class TorrentProvider:
    def __init__(self, name, base_url):
        self.name = name
        self.base_url = base_url
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    def search(self, query):
        raise NotImplementedError

class LimeTorrentsProvider(TorrentProvider):
    def search(self, query):
        url = f"{self.base_url}/search/all/{query.replace(' ', '-')}/"
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            table = soup.find('table', class_='table2')
            if not table: return []

            results = []
            for row in table.find_all('tr')[1:]:
                name_div = row.find('div', class_='tt-name')
                if not name_div: continue
                links = name_div.find_all('a')
                if len(links) < 2: continue
                
                td_normals = row.find_all('td', class_='tdnormal')
                if len(td_normals) < 2: continue

                results.append({
                    'source': self.name,
                    'title': links[1].text.strip(),
                    'link': links[0]['href'],
                    'size': td_normals[1].text.strip(),
                    'seeds': row.find('td', class_='tdseed').text.strip(),
                    'leeches': row.find('td', class_='tdleech').text.strip()
                })
            return results
        except Exception as e:
            print(f"Erreur {self.name}: {e}")
            return []

def main():
    parser = argparse.ArgumentParser(description="Bot de recherche de torrents")
    parser.add_argument("query", help="Le terme de recherche")
    parser.add_argument("-vf", "--vf", action="store_true", help="Ajouter 'FRENCH' et 'VF' à la recherche")
    parser.add_argument("-n", "--num", type=int, default=15, help="Nombre de résultats")
    
    args = parser.parse_args()
    
    query = args.query
    if args.vf:
        query += " FRENCH VF"
    
    providers = [
        LimeTorrentsProvider("LimeTorrents", "https://www.limetorrents.info")
    ]
    
    all_results = []
    print(f"Recherche de : '{query}'...")
    for provider in providers:
        all_results.extend(provider.search(query))
    
    if not all_results:
        print("Aucun résultat trouvé.")
        return

    # Tri par seeds
    all_results.sort(key=lambda x: int(x['seeds'].replace(',', '')) if x['seeds'].replace(',', '').isdigit() else 0, reverse=True)

    print(f"\n{'#' :<3} | {'Source':<12} | {'Titre':<60} | {'Taille':<10} | {'S/L':<8}")
    print("-" * 105)
    
    for i, res in enumerate(all_results[:args.num], 1):
        s_l = f"{res['seeds']}/{res['leeches']}"
        title = (res['title'][:57] + '..') if len(res['title']) > 57 else res['title']
        print(f"{i:<3} | {res['source']:<12} | {title:<60} | {res['size']:<10} | {s_l:<8}")

    while True:
        choice = input("\nEntrez un numéro pour le lien (ou 'q' pour quitter) : ")
        if choice.lower() == 'q': break
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(all_results):
                res = all_results[idx]
                print(f"\nTitre  : {res['title']}")
                print(f"Source : {res['source']}")
                print(f"Lien   : {res['link']}")
            else:
                print("Invalide.")
        except ValueError:
            print("Entrez un nombre.")

if __name__ == "__main__":
    main()
