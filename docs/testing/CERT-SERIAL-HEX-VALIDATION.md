# Plan de test — affichage serial hex (détails certificat)

**Branche** : `feat/cert-serial-hex-display`  
**Portée** : UI certificats — section **Détails techniques** + utilitaire `formatSerialNumberHex`

---

## 1. Tests automatisés (obligatoires)

### Frontend (Vitest)

```bash
cd frontend
npm run test -- src/lib/__tests__/utils.test.js --run
```

| ID | Cas | Attendu |
|----|-----|---------|
| T1 | Serial décimal UCM (`4065849396…`) | `47:37:E6:35:…:D3:0B` |
| T2 | Hex compact (`4737E635…`) | Même sortie colon-séparée uppercase |
| T3 | Hex déjà avec `:` (minuscules) | Normalisé uppercase |
| T4 | Entrée vide / invalide | `null` |

Critère : **39/39 passed** (suite `utils.test.js` incluant les 4 cas ci-dessus).

### Backend (pytest — régression)

Pas de changement backend ; exécuter la suite complète avant merge :

```bash
cd backend
pytest -q --tb=no
```

Critère : **0 failed** (warnings acceptables).

---

## 2. Test manuel UI

1. Ouvrir **Certificats** → sélectionner un certificat émis par UCM.
2. Panneau **Détails techniques** :
   - **Série** : valeur décimale (ex. `406584939640065587371689749107479415526363616011`)
   - **Série (hex)** : format navigateur (ex. `47:37:E6:35:30:D7:EA:91:39:2B:51:4E:34:55:DB:E2:2E:A1:D3:0B`)
3. Copier la valeur hex (bouton copy) → coller dans `openssl x509 -serial` ou comparer au certificat PEM.
4. Langue FR : libellé **Série (hex)** ; EN : **Serial (hex)**.

---

## 3. Correspondance serial / OCSP

| Décimal (UCM) | Hex (UI / navigateur) |
|---------------|------------------------|
| `406584939640065587371689749107479415526363616011` | `47:37:E6:35:30:D7:EA:91:39:2B:51:4E:34:55:DB:E2:2E:A1:D3:0B` |
| `316154770811771731777519343495635219991455236293` | `37:60:DE:C7:AF:D7:7B:9A:B8:9D:86:BF:BD:08:D1:05:BA:A6:80:C5` |

Vérification OpenSSL :

```bash
openssl x509 -in cert.pem -noout -serial
# serial=4737E63530D7EA91392B514E3455DBE22EA1D30B  → même valeur sans les ':'
```

---

## 4. Résultats validation (2026-07-03)

| Contrôle | Résultat |
|----------|----------|
| Vitest `utils.test.js` | **39 passed** |
| pytest backend | voir CI / exécution locale |
| Déploiement lab privé | Build + dist déployé, champ visible après hard refresh |

---

## Fichiers modifiés

- `frontend/src/lib/utils.js` — `formatSerialNumberHex()`
- `frontend/src/components/CertificateDetails.jsx` — champ **Série (hex)**
- `frontend/src/lib/__tests__/utils.test.js` — tests T1–T4
- `frontend/src/i18n/locales/*.json` — clé `common.serialHex` (9 langues)
