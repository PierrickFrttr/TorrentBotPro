# 🎬 TorrentBot Pro : Votre Cinéma à la Maison (Guide Débutant) 🚀

Bienvenue ! Ce guide va vous accompagner pas à pas pour installer votre propre système de recherche et de diffusion de films. Pas besoin d'être un expert en informatique, suivez simplement les étapes dans l'ordre.

## ❓ C'est quoi TorrentBot Pro ?
Imaginez un outil unique où vous tapez le nom d'un film, et en deux clics, il est trouvé, téléchargé et disponible sur votre téléviseur ou votre téléphone, avec sa belle affiche et son résumé. C'est ce que nous allons installer.

---

## 🛠️ Étape 1 : Installer les outils nécessaires
Avant de lancer le bot, nous avons besoin de 3 "ouvriers" qui vont travailler pour nous :

1.  **Python (Le Moteur)** : C'est ce qui permet au Bot de fonctionner.
    - Téléchargez-le sur [python.org](https://www.python.org/downloads/).
    - **IMPORTANT** : Pendant l'installation, cochez bien la case **"Add Python to PATH"**.
2.  **qBittorrent (Le Livreur)** : C'est lui qui télécharge les fichiers.
    - Téléchargez-le sur [qbittorrent.org](https://www.qbittorrent.org/download.php).
3.  **Jackett (Le Documentaliste)** : C'est lui qui cherche sur tous les sites à votre place.
    - Il est déjà inclus dans votre dossier `TorrentBot\Jackett`.

---

## ⚙️ Étape 2 : Configurer le dossier de films
Nous allons créer un endroit propre où tous vos films seront rangés.
1.  Créez un dossier nommé **"Ma Bibliothèque"** (par exemple dans vos Vidéos).
2.  Ouvrez **qBittorrent**.
3.  Allez dans `Outils` > `Options` > `Téléchargements`.
4.  Dans "Chemin de sauvegarde par défaut", sélectionnez votre dossier **"Ma Bibliothèque"**.
5.  Désormais, tout ce que vous téléchargerez ira directement là-dedans.

---

## 🔍 Étape 3 : Préparer la recherche (Jackett)
C'est ici que le Bot va puiser ses informations.
1.  Lancez le fichier `JackettConsole.exe` dans votre dossier Jackett.
2.  Une page internet s'ouvre. Si ce n'est pas le cas, allez sur [http://127.0.0.1:9117](http://127.0.0.1:9117).
3.  Cliquez sur le bouton vert **"Add Indexer"**.
4.  Cherchez des sites comme "Torrent9" ou "Limetorrents" et cliquez sur le petit **+** vert pour les ajouter.
5.  **TRÈS IMPORTANT** : En haut à droite de cette page, vous verrez un code appelé **"API Key"**. Copiez ce code, nous en aurons besoin juste après.

---

## 🤖 Étape 4 : Lancer votre Bot
C'est votre outil de commande.
1.  Allez dans le dossier `Scripts` de TorrentBot.
2.  Faites un clic droit sur `torrent_gui.py` et ouvrez-le avec un éditeur de texte (comme le Bloc-notes).
3.  Cherchez la ligne `API_KEY = "..."` et collez votre code copié à l'étape précédente entre les guillemets.
4.  Enregistrez et fermez.
5.  Utilisez le raccourci sur votre bureau pour lancer l'application !

---

## 📺 Étape 5 : Regarder sur la télé (Jellyfin)
Pour voir vos films avec des affiches comme sur Netflix :
1.  Installez **Jellyfin Server** sur votre PC.
2.  Lorsqu'il vous demande où sont vos films, montrez-lui votre dossier **"Ma Bibliothèque"**.
3.  Sur votre Android TV ou votre téléphone, installez l'application **Jellyfin**.
4.  Connectez-vous et profitez !

---

## 📖 Comment utiliser le Bot au quotidien ?
1.  Allumez votre PC (Jackett et Jellyfin se lancent tout seuls en arrière-plan).
2.  Lancez le raccourci **"Mon Torrent Bot"** sur votre bureau.
3.  Tapez le nom d'un film (ex: "Bambi VF") et appuyez sur **Entrée**.
4.  **Double-cliquez** sur le meilleur résultat dans la liste.
5.  Le téléchargement démarre dans qBittorrent. Une fois fini, le film apparaît magiquement sur votre télé dans l'appli Jellyfin !

---
*Note : Ce guide est fait pour vous aider à centraliser vos contenus légaux et personnels. Respectez toujours les lois sur le droit d'auteur dans votre pays.*
