export default {
  helpContent: {
    title: 'Navigazione',
    subtitle: 'La barra superiore, il menu Moduli e i moduli fissati',
    overview: 'La barra superiore contiene le pagine principali, fino a tre moduli che fissi, il menu Moduli, la ricerca e il tuo account. Il menu Moduli elenca tutte le pagine che puoi aprire, in quattro gruppi; le pagine per cui non hai i diritti non vengono mostrate.',
    sections: [
      {
        title: 'Menu Moduli',
        items: [
          { label: 'Apri', text: 'Seleziona Moduli, oppure premi Freccia giù sul pulsante; il focus passa alla prima pagina' },
          { label: 'Spostati', text: 'Freccia su, Freccia giù, Home e Fine ti spostano tra le pagine; Esc chiude il menu e torna al pulsante' },
          { label: 'Fissa', text: 'Il pulsante a forma di puntina accanto a una pagina la mantiene nella barra superiore; al massimo tre, e il menu lo segnala se ne provi una quarta' },
        ]
      },
      {
        title: 'Ricerca e scorciatoie',
        items: [
          { label: 'Ricerca', text: 'Premi Ctrl K (Cmd K su macOS) o seleziona il campo di ricerca per andare a una pagina o trovare un certificato' },
          { label: 'Aiuto', text: 'Premi ? fuori da un campo di testo per aprire la guida della pagina corrente' },
          { label: 'Larghezza telefono', text: 'La barra superiore mostra un unico elenco di pagine al posto dei link e del menu' },
        ]
      },
      {
        title: 'Menu dell\'account',
        items: [
          { label: 'Account', text: 'Il tuo profilo e le tue impostazioni, la lingua e la disconnessione' },
        ]
      },
      {
        title: 'Menu del tema',
        items: [
          { label: 'Scegli', text: 'Il pulsante sole o luna imposta il tema di colori e la modalità; Sistema segue il tuo dispositivo, e l\'icona mostra la modalità applicata' },
          { label: 'Tastiera', text: 'Freccia su e Freccia giù scorrono le opzioni in modo circolare; Esc o Tab chiude il menu e torna al pulsante' },
          { label: 'Salvato', text: 'La scelta è quella in Impostazioni, Aspetto, e ti segue in ogni browser' },
        ]
      },
      {
        title: 'Notifiche',
        items: [
          { label: 'Campanella', text: 'Il contatore è il numero di elementi non letti nel pannello: elementi critici e approvazioni dalla coda della panoramica, e backup pianificati falliti o sessioni revocate dal registro di audit' },
          { label: 'Ordine', text: 'Prima gli elementi della coda, poi quelli del registro di audit, dal più recente' },
          { label: 'Diritti', text: 'Vedi solo gli elementi delle fonti che puoi leggere; una fonte su cui non hai diritti non mostra nulla' },
          { label: 'Lette', text: 'Segna come letto un elemento o tutti; i segni sono salvati con le tue preferenze, e un elemento risolto esce dal pannello' },
          { label: 'Apri', text: 'Apri porta alla pagina dell\'elemento; dal pannello non si approva né si riprova nulla' },
        ]
      },
    ],
    tips: [
      'I tuoi elementi fissati ti seguono in ogni browser e dispositivo da cui accedi',
      'Una pagina fissata che non hai più il diritto di aprire viene nascosta, e ritorna se il diritto viene ripristinato prima che tu cambi i fissati',
    ],
  },
}
