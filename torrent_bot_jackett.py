import argparse
import jackett_client


def main():
    parser = argparse.ArgumentParser(description="Bot de recherche Torrent via Jackett")
    parser.add_argument("query", help="Le film, série ou logiciel à chercher")
    args = parser.parse_args()

    print(f"Recherche globale pour : '{args.query}'...")

    try:
        results = jackett_client.search(args.query)
    except (ConnectionError, RuntimeError) as e:
        print(f"\n{e}")
        print("Conseils :")
        print("1. Vérifie que Jackett est lancé (JackettConsole.exe).")
        print("2. Vérifie que tu as ajouté des indexers dans l'interface Jackett.")
        return

    if not results:
        print("\nAucun résultat trouvé.")
        return

    print(f"\n{'#' :<3} | {'Indexer':<15} | {'Titre':<60} | {'S':<5} | {'Taille':<10}")
    print("-" * 105)
    for i, res in enumerate(results[:20], 1):
        title = (res["title"][:57] + "..") if len(res["title"]) > 57 else res["title"]
        print(f"{i:<3} | {res['indexer']:<15} | {title:<60} | {res['seeders']:<5} | {res['size']:<10}")

    while True:
        choice = input("\nEntrez un numéro pour obtenir le lien (ou 'q' pour quitter) : ")
        if choice.lower() == "q":
            break
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(results):
                target = results[idx]
                print(f"\n--- DÉTAILS DU TORRENT ---")
                print(f"Titre   : {target['title']}")
                print(f"Indexer : {target['indexer']}")
                print(f"Lien    : {target['magnet']}")
                print(f"--------------------------")
            else:
                print("Numéro invalide.")
        except ValueError:
            print("Veuillez entrer un nombre valide.")


if __name__ == "__main__":
    main()
