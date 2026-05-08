import tkinter as tk
from tkinter import messagebox, ttk
import requests
import webbrowser
import os

# --- CONFIGURATION ---
JACKETT_URL = "http://127.0.0.1:9117"
JELLYFIN_URL = "http://localhost:8096"
API_KEY = "puqye2oamnc81mr8mqrvfe605adq8wbi"
# ---------------------

class ModernTorrentGui:
    def __init__(self, root):
        self.root = root
        self.root.title("Torrent Search Pro")
        self.root.geometry("1000x700")
        self.root.configure(bg="#1e1e2e")  # Fond sombre moderne (style Catppuccin/VSCode)
        
        # Couleurs
        self.colors = {
            "bg": "#1e1e2e",
            "sidebar": "#181825",
            "accent": "#89b4fa",
            "text": "#cdd6f4",
            "subtext": "#a6adc8",
            "green": "#a6e3a1",
            "red": "#f38ba8",
            "entry_bg": "#313244"
        }

        self.setup_styles()
        self.create_widgets()
        self.results_data = []

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("default")
        
        # Style pour le tableau (Treeview)
        style.configure("Treeview", 
            background=self.colors["entry_bg"], 
            foreground=self.colors["text"],
            fieldbackground=self.colors["entry_bg"],
            rowheight=35,
            borderwidth=0,
            font=("Segoe UI", 10)
        )
        style.map("Treeview", background=[('selected', self.colors["accent"])])
        
        # Style des entêtes du tableau
        style.configure("Treeview.Heading", 
            background=self.colors["sidebar"], 
            foreground=self.colors["accent"],
            font=("Segoe UI", 11, "bold"),
            borderwidth=0
        )

    def create_widgets(self):
        # --- HEADER ---
        header = tk.Frame(self.root, bg=self.colors["sidebar"], height=80)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        title_label = tk.Label(header, text="TORRENT SEARCH", font=("Segoe UI", 18, "bold"), 
                               bg=self.colors["sidebar"], fg=self.colors["accent"])
        title_label.pack(side=tk.LEFT, padx=30, pady=20)

        # Bouton pour gérer Jackett
        self.manage_btn = tk.Button(header, text="GÉRER LES SOURCES", command=self.open_jackett_web,
                                    bg=self.colors["entry_bg"], fg=self.colors["accent"],
                                    font=("Segoe UI", 9, "bold"), borderwidth=1,
                                    highlightbackground=self.colors["accent"],
                                    padx=15, pady=5, cursor="hand2", activebackground=self.colors["accent"],
                                    activeforeground=self.colors["sidebar"])
        self.manage_btn.pack(side=tk.RIGHT, padx=20, pady=20)

        # Bouton pour ouvrir Jellyfin
        self.jellyfin_btn = tk.Button(header, text="BIBLIOTHÈQUE (JELLYFIN)", command=self.open_jellyfin_web,
                                    bg=self.colors["entry_bg"], fg=self.colors["green"],
                                    font=("Segoe UI", 9, "bold"), borderwidth=1,
                                    padx=15, pady=5, cursor="hand2", activebackground=self.colors["green"],
                                    activeforeground=self.colors["sidebar"])
        self.jellyfin_btn.pack(side=tk.RIGHT, padx=10, pady=20)

        # --- SEARCH BAR AREA ---
        search_container = tk.Frame(self.root, bg=self.colors["bg"], pady=30)
        search_container.pack(fill=tk.X)

        inner_search = tk.Frame(search_container, bg=self.colors["bg"])
        inner_search.pack()

        # Champ de saisie stylisé
        self.search_entry = tk.Entry(inner_search, font=("Segoe UI", 14), width=40, 
                                     bg=self.colors["entry_bg"], fg=self.colors["text"],
                                     insertbackground=self.colors["text"], borderwidth=0,
                                     highlightthickness=2, highlightbackground=self.colors["entry_bg"],
                                     highlightcolor=self.colors["accent"])
        self.search_entry.pack(side=tk.LEFT, padx=10, ipady=5)
        self.search_entry.bind('<Return>', lambda e: self.perform_search())
        self.search_entry.insert(0, "Rechercher un film, une série...")

        # Bouton de recherche
        self.search_btn = tk.Button(inner_search, text="RECHERCHER", command=self.perform_search,
                                    bg=self.colors["accent"], fg=self.colors["sidebar"],
                                    font=("Segoe UI", 11, "bold"), borderwidth=0,
                                    padx=20, cursor="hand2", activebackground=self.colors["subtext"])
        self.search_btn.pack(side=tk.LEFT, padx=10)

        # --- RESULTS TABLE ---
        table_frame = tk.Frame(self.root, bg=self.colors["bg"])
        table_frame.pack(fill=tk.BOTH, expand=True, padx=30, pady=10)

        self.tree = ttk.Treeview(table_frame, columns=("Indexer", "Titre", "S", "Taille"), show="headings")
        self.tree.heading("Indexer", text="SOURCE")
        self.tree.heading("Titre", text="TITRE DU FICHIER")
        self.tree.heading("S", text="SEEDS")
        self.tree.heading("Taille", text="TAILLE")
        
        self.tree.column("Indexer", width=120, anchor="w")
        self.tree.column("Titre", width=600, anchor="w")
        self.tree.column("S", width=80, anchor="center")
        self.tree.column("Taille", width=120, anchor="center")
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Scrollbar moderne
        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # --- FOOTER / STATUS ---
        self.status_label = tk.Label(self.root, text="Prêt pour une nouvelle recherche", 
                                     font=("Segoe UI", 9), bg=self.colors["bg"], fg=self.colors["subtext"], pady=10)
        self.status_label.pack()

        # Info instructions
        info_label = tk.Label(self.root, text="Double-cliquez sur une ligne pour lancer le téléchargement dans qBittorrent", 
                              font=("Segoe UI", 10, "italic"), bg=self.colors["sidebar"], fg=self.colors["green"], pady=15)
        info_label.pack(fill=tk.X)

        self.tree.bind("<Double-1>", self.open_magnet)

    def perform_search(self):
        query = self.search_entry.get()
        if not query or query == "Rechercher un film, une série...":
            return
        
        self.status_label.config(text=f"Recherche de '{query}' en cours...", fg=self.colors["accent"])
        self.search_btn.config(state=tk.DISABLED, bg=self.colors["entry_bg"])
        self.root.update()
        
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # On essaie 127.0.0.1 puis localhost pour éviter les problèmes DNS/IPv6
        success = False
        last_error = ""
        
        for host in ["127.0.0.1", "localhost"]:
            url = f"http://{host}:9117/api/v2.0/indexers/all/results"
            params = {'apikey': API_KEY, 'Query': query}
            
            try:
                r = requests.get(url, params=params, timeout=10)
                r.raise_for_status()
                data = r.json()
                
                self.results_data = data.get('Results', [])
                self.results_data.sort(key=lambda x: x.get('Seeders', 0), reverse=True)
                
                for i, item in enumerate(self.results_data[:100]):
                    size_bytes = item.get('Size', 0)
                    if size_bytes > 1024**3:
                        size_str = f"{size_bytes / (1024**3):.2f} GB"
                    else:
                        size_str = f"{size_bytes / (1024**2):.2f} MB"
                    
                    # Sécurisation du nom de la source et du titre
                    source_name = str(item.get('IndexerName') or "INCONNU").upper()
                    title = item.get('Title') or "Sans titre"
                    
                    self.tree.insert("", tk.END, iid=i, values=(
                        source_name,
                        title,
                        item.get('Seeders', 0),
                        size_str
                    ))
                
                self.status_label.config(text=f"{len(self.results_data)} résultats trouvés", fg=self.colors["green"])
                success = True
                break
                    
            except Exception as e:
                last_error = str(e)
                continue
        
        if not success:
            self.status_label.config(text="Erreur de connexion", fg=self.colors["red"])
            messagebox.showerror("Erreur", f"Jackett ne répond pas.\n\nDétails : {last_error}\n\nAssure-toi que JackettConsole.exe est bien lancé.")
        
        self.search_btn.config(state=tk.NORMAL, bg=self.colors["accent"])

    def open_magnet(self, event):
        selected_item = self.tree.selection()
        if not selected_item:
            return
        
        idx = int(selected_item[0])
        item = self.results_data[idx]
        magnet = item.get('MagnetUri') or item.get('Link')
        
        if magnet:
            self.status_label.config(text="Envoi vers qBittorrent...", fg=self.colors["green"])
            webbrowser.open(magnet)
        else:
            messagebox.showwarning("Lien manquant", "Ce résultat ne contient pas de lien valide.")

    def open_jackett_web(self):
        webbrowser.open(JACKETT_URL)

    def open_jellyfin_web(self):
        webbrowser.open(JELLYFIN_URL)

if __name__ == "__main__":
    root = tk.Tk()
    # On enlève la bordure Windows classique pour un look plus "App"
    # root.overrideredirect(True) # Optionnel : enlève la barre de titre
    app = ModernTorrentGui(root)
    root.mainloop()
