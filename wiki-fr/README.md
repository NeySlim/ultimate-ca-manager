# 📚 UCM Wiki - Instructions de Publication

Ce dossier contient les pages wiki de Ultimate CA Manager.

---

## 📁 Pages Créées

1. **Home.md** (2.7 KB) - Page d'accueil du wiki
2. **Quick-Start.md** (4.5 KB) - Guide de démarrage rapide (10 minutes)
3. **User-Manual.md** (17 KB) - Manuel utilisateur complet
4. **FAQ.md** (11 KB) - Questions fréquemment posées
5. **Troubleshooting.md** (11 KB) - Guide de dépannage
6. **API-Reference.md** (13 KB) - Documentation API REST

**Total**: ~59 KB de documentation

---

## 🚀 Publier le Wiki sur GitHub

GitHub Wiki utilise un repository Git séparé. Voici comment publier :

### Méthode 1: Via Interface Web (Recommandé pour première publication)

1. **Activer le Wiki**
   ```
   https://github.com/NeySlim/ultimate-ca-manager/settings
   → Features → ✅ Wikis
   → Save
   ```

2. **Créer la première page**
   ```
   https://github.com/NeySlim/ultimate-ca-manager/wiki
   → Create the first page
   → Title: Home
   → Copier-coller le contenu de wiki/Home.md
   → Save Page
   ```

3. **Créer les autres pages**
   - Cliquer "New Page" pour chaque fichier
   - Title = nom du fichier sans .md (ex: "Quick-Start")
   - Copier-coller le contenu correspondant
   - Répéter pour toutes les pages

### Méthode 2: Via Git (Recommandé pour mises à jour)

1. **Cloner le Wiki repository**
   ```bash
   cd /tmp
   git clone https://github.com/NeySlim/ultimate-ca-manager.wiki.git
   cd ultimate-ca-manager.wiki
   ```

2. **Copier les fichiers**
   ```bash
   cp /root/ucm-src/wiki/*.md .
   ```

3. **Commit et Push**
   ```bash
   git add *.md
   git commit -m "docs: Add comprehensive wiki documentation
   
   - Home page with navigation
   - Quick Start guide (10 min setup)
   - Complete User Manual (17 KB)
   - FAQ with common questions
   - Troubleshooting guide
   - API REST reference
   "
   git push origin master
   ```

### Méthode 3: Script Automatique

Utiliser le script `publish-wiki.sh` inclus dans ce dossier :

```bash
cd /root/ucm-src/wiki
chmod +x publish-wiki.sh
./publish-wiki.sh
```

---

## 🔄 Mettre à Jour le Wiki

### Modification d'une page

```bash
# 1. Modifier le fichier localement
nano /root/ucm-src/wiki/User-Manual.md

# 2. Cloner le wiki (si pas déjà fait)
cd /tmp
git clone https://github.com/NeySlim/ultimate-ca-manager.wiki.git
cd ultimate-ca-manager.wiki

# 3. Copier la version modifiée
cp /root/ucm-src/wiki/User-Manual.md .

# 4. Commit et push
git add User-Manual.md
git commit -m "docs: Update User Manual"
git push origin master
```

### Ajout d'une nouvelle page

```bash
# 1. Créer le fichier
cd /root/ucm-src/wiki
nano New-Page.md

# 2. L'ajouter au wiki
cd /tmp/ultimate-ca-manager.wiki
cp /root/ucm-src/wiki/New-Page.md .
git add New-Page.md
git commit -m "docs: Add New Page"
git push origin master

# 3. Mettre à jour Home.md pour lien vers nouvelle page
```

---

## 📝 Conventions de Nommage

### Fichiers
- **Format**: `Page-Title.md` (PascalCase avec tirets)
- **Exemples**: 
  - `Home.md`
  - `Quick-Start.md`
  - `User-Manual.md`
  - `API-Reference.md`

### Liens Internes
```markdown
[Texte du lien](Page-Title)
```

**Exemples**:
```markdown
[Quick Start](Quick-Start)
[User Manual](User-Manual)
[FAQ](FAQ#section-specifique)
```

### Sections
```markdown
## Section Principale
### Sous-section
#### Sous-sous-section
```

---

## 🖼️ Images

### Ajouter des Images

1. **Upload via web**
   ```
   Wiki → Edit Page → Upload Image (drag & drop)
   ```

2. **Via Git**
   ```bash
   cd /tmp/ultimate-ca-manager.wiki
   mkdir -p images
   cp screenshot.png images/
   git add images/screenshot.png
   git commit -m "docs: Add screenshot"
   git push
   ```

3. **Référencer l'image**
   ```markdown
   ![Description](images/screenshot.png)
   ```

### Images depuis le Repository Principal

```markdown
![Architecture](https://github.com/NeySlim/ultimate-ca-manager/blob/main/docs/diagrams/architecture.png?raw=true)
```

---

## ✅ Checklist de Publication

Avant de publier:

- [ ] Toutes les pages créées (6 pages minimum)
- [ ] Liens internes vérifiés
- [ ] Orthographe et grammaire vérifiées
- [ ] Code examples testés
- [ ] Screenshots ajoutés (si disponibles)
- [ ] Home.md à jour avec tous les liens
- [ ] Navigation cohérente entre pages

Après publication:

- [ ] Vérifier rendu sur GitHub Wiki
- [ ] Tester tous les liens
- [ ] Vérifier images s'affichent
- [ ] Navigation fonctionne
- [ ] Recherche wiki fonctionne

---

## 🎯 Prochaines Pages à Ajouter (Optionnel)

1. **Installation-Guide.md** - Guide installation détaillé
2. **CA-Management.md** - Gestion approfondie des CAs
3. **Certificate-Operations.md** - Opérations certificats avancées
4. **SCEP-Configuration.md** - Configuration SCEP détaillée
5. **System-Configuration.md** - Configuration système
6. **User-Management.md** - Gestion utilisateurs et RBAC
7. **Security-Best-Practices.md** - Bonnes pratiques sécurité
8. **Migration-Guide.md** - Guide de migration
9. **Integrations.md** - Intégrations iOS, Android, etc.

---

## 📞 Support

Questions sur la publication du wiki ?

- **GitHub Docs**: https://docs.github.com/en/communities/documenting-your-project-with-wikis
- **Markdown Guide**: https://docs.github.com/en/get-started/writing-on-github

---

**Status**: ✅ 6 pages prêtes à publier (~59 KB)  
**Dernière mise à jour**: Janvier 2026
