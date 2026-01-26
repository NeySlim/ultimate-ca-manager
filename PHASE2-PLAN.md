# PHASE 2: CORE PAGES MIGRATION

**Objectif:** Migrer Dashboard, CAs, Certificates vers le nouveau design system

## Pages à Migrer:

### 1. Dashboard.jsx
- [ ] Remplacer old Button par design-system Button
- [ ] Remplacer old Badge par design-system Badge  
- [ ] Remplacer old Spinner par design-system Spinner
- [ ] Utiliser Stack/Grid pour layout
- [ ] Ajouter animations (stagger sur stats)
- [ ] Tester avec API réelle

### 2. CAList.jsx
- [ ] Remplacer composants UI
- [ ] Utiliser DataTable avec design system
- [ ] Modal avec nouveau design
- [ ] Ajouter hover effects
- [ ] Tester CRUD operations

### 3. CertificateList.jsx
- [ ] Remplacer composants UI
- [ ] Badges colorés pour statuts
- [ ] Filtres avec nouveaux inputs
- [ ] Animations sur actions
- [ ] Tester émission/révocation

## Stratégie:
1. Commencer par Dashboard (plus simple)
2. Migrer progressivement les imports
3. Garder la logique métier intacte
4. Tester après chaque migration
5. Screenshots avant/après
