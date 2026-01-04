# 📚 UCM Wiki - Publication Instructions

This folder contains the English wiki pages for Ultimate CA Manager.

**French version available in**: `wiki-fr/`

---

## 📁 Pages Created

1. **Home.md** (2.7 KB) - Wiki homepage
2. **Quick-Start.md** (4.5 KB) - 10-minute quick start guide  
3. **User-Manual.md** - Complete user manual (TO BE TRANSLATED)
4. **FAQ.md** - Frequently asked questions (TO BE TRANSLATED)
5. **Troubleshooting.md** - Troubleshooting guide (TO BE TRANSLATED)
6. **API-Reference.md** - REST API documentation (TO BE TRANSLATED)

**Status**: Home and Quick-Start ready in English. Technical pages can remain in French or be translated gradually.

---

## 🚀 Publish Wiki to GitHub

GitHub Wiki uses a separate Git repository. Here's how to publish:

### Method 1: Web Interface (Recommended for first publication)

1. **Enable Wiki**
   ```
   https://github.com/NeySlim/ultimate-ca-manager/settings
   → Features → ✅ Wikis
   → Save
   ```

2. **Create first page**
   ```
   https://github.com/NeySlim/ultimate-ca-manager/wiki
   → Create the first page
   → Title: Home
   → Copy content from wiki/Home.md
   → Save Page
   ```

3. **Create other pages**
   - Click "New Page" for each file
   - Title = filename without .md (e.g., "Quick-Start")
   - Copy-paste corresponding content
   - Repeat for all pages

### Method 2: Via Git (Recommended for updates)

1. **Clone Wiki repository**
   ```bash
   cd /tmp
   git clone https://github.com/NeySlim/ultimate-ca-manager.wiki.git
   cd ultimate-ca-manager.wiki
   ```

2. **Copy files**
   ```bash
   cp /root/ucm-src/wiki/*.md .
   rm -f README.md publish-wiki.sh
   ```

3. **Commit and Push**
   ```bash
   git add *.md
   git commit -m "docs: Publish wiki documentation"
   git push origin master
   ```

### Method 3: Automated Script

Use the included `publish-wiki.sh` script:

```bash
cd /root/ucm-src/wiki
chmod +x publish-wiki.sh
./publish-wiki.sh
```

---

## 🔄 Update Wiki

### Modify a page

```bash
# 1. Edit file locally
nano /root/ucm-src/wiki/User-Manual.md

# 2. Clone wiki (if not done)
cd /tmp
git clone https://github.com/NeySlim/ultimate-ca-manager.wiki.git
cd ultimate-ca-manager.wiki

# 3. Copy modified version
cp /root/ucm-src/wiki/User-Manual.md .

# 4. Commit and push
git add User-Manual.md
git commit -m "docs: Update User Manual"
git push origin master
```

### Add a new page

```bash
# 1. Create file
cd /root/ucm-src/wiki
nano New-Page.md

# 2. Add to wiki
cd /tmp/ultimate-ca-manager.wiki
cp /root/ucm-src/wiki/New-Page.md .
git add New-Page.md
git commit -m "docs: Add New Page"
git push origin master

# 3. Update Home.md to link to new page
```

---

## 📝 Naming Conventions

### Files
- **Format**: `Page-Title.md` (PascalCase with hyphens)
- **Examples**: 
  - `Home.md`
  - `Quick-Start.md`
  - `User-Manual.md`
  - `API-Reference.md`

### Internal Links
```markdown
[Link text](Page-Title)
```

**Examples**:
```markdown
[Quick Start](Quick-Start)
[User Manual](User-Manual)
[FAQ](FAQ#specific-section)
```

---

## 🖼️ Images

### Add Images

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

3. **Reference image**
   ```markdown
   ![Description](images/screenshot.png)
   ```

### Images from Main Repository

```markdown
![Architecture](https://github.com/NeySlim/ultimate-ca-manager/blob/main/docs/diagrams/architecture.png?raw=true)
```

---

## ✅ Publication Checklist

Before publishing:

- [ ] All pages created
- [ ] Internal links verified
- [ ] Spelling and grammar checked
- [ ] Code examples tested
- [ ] Screenshots added (if available)
- [ ] Home.md updated with all links
- [ ] Navigation consistent between pages

After publishing:

- [ ] Verify rendering on GitHub Wiki
- [ ] Test all links
- [ ] Verify images display
- [ ] Navigation works
- [ ] Wiki search works

---

## 🌍 Language Versions

- **English** (primary): `/wiki/`
- **French** (reference): `/wiki-fr/`

Technical pages (API, Troubleshooting) work well in either language as they're mostly code.

---

## 📞 Support

Questions about wiki publication?

- **GitHub Docs**: https://docs.github.com/en/communities/documenting-your-project-with-wikis
- **Markdown Guide**: https://docs.github.com/en/get-started/writing-on-github

---

**Status**: ✅ Ready to publish  
**Last update**: January 2026
