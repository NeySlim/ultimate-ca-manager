export default {
  helpContent: {
    title: 'Navigation',
    subtitle: 'Die obere Leiste, das Modulmenü und angeheftete Module',
    overview: 'Die obere Leiste enthält die Hauptseiten, bis zu drei angeheftete Module, das Modulmenü, die Suche und Ihr Konto. Das Modulmenü listet alle Seiten auf, die Sie öffnen dürfen, in vier Gruppen; Seiten ohne Berechtigung werden nicht angezeigt.',
    sections: [
      {
        title: 'Modulmenü',
        items: [
          { label: 'Öffnen', text: 'Wählen Sie Module oder drücken Sie die Pfeiltaste nach unten auf der Schaltfläche; der Fokus springt zur ersten Seite' },
          { label: 'Bewegen', text: 'Pfeil nach oben, Pfeil nach unten, Pos1 und Ende wechseln zwischen den Seiten; Esc schließt das Menü und kehrt zur Schaltfläche zurück' },
          { label: 'Anheften', text: 'Die Anheften-Schaltfläche neben einer Seite behält sie in der oberen Leiste; höchstens drei, und das Menü weist darauf hin, wenn Sie eine vierte versuchen' },
        ]
      },
      {
        title: 'Suche und Tastenkürzel',
        items: [
          { label: 'Suche', text: 'Drücken Sie Strg K (Cmd K unter macOS) oder wählen Sie das Suchfeld, um zu einer Seite zu springen oder ein Zertifikat zu finden' },
          { label: 'Hilfe', text: 'Drücken Sie ? außerhalb eines Textfelds, um die Hilfe der aktuellen Seite zu öffnen' },
          { label: 'Telefonbreite', text: 'Die obere Leiste zeigt statt der Links und des Menüs eine einzige Seitenliste' },
        ]
      },
      {
        title: 'Kontomenü',
        items: [
          { label: 'Konto', text: 'Ihr Profil und Ihre Einstellungen, Sprache und Abmelden' },
        ]
      },
      {
        title: 'Designmenü',
        items: [
          { label: 'Auswählen', text: 'Die Sonnen- oder Mondschaltfläche legt das Farbdesign und den Modus fest; System folgt Ihrem Gerät, und das Symbol zeigt den angewendeten Modus' },
          { label: 'Tastatur', text: 'Pfeil nach oben und Pfeil nach unten wechseln zyklisch zwischen den Optionen; Esc oder Tab schließt das Menü und kehrt zur Schaltfläche zurück' },
          { label: 'Gespeichert', text: 'Die Auswahl entspricht der unter Einstellungen, Darstellung und folgt Ihnen in jeden Browser' },
        ]
      },
      {
        title: 'Benachrichtigungen',
        items: [
          { label: 'Glocke', text: 'Die Zahl entspricht den ungelesenen Einträgen im Panel: kritische Einträge und Genehmigungen aus der Dashboard-Warteschlange sowie fehlgeschlagene geplante Sicherungen oder widerrufene Sitzungen aus dem Audit-Protokoll' },
          { label: 'Reihenfolge', text: 'Zuerst die Einträge der Warteschlange, dann die des Audit-Protokolls, jeweils die neuesten zuerst' },
          { label: 'Berechtigungen', text: 'Sie sehen nur Einträge aus Quellen, die Sie lesen dürfen; eine Quelle ohne Berechtigung zeigt nichts an' },
          { label: 'Gelesen', text: 'Markieren Sie einen Eintrag oder alle als gelesen; die Markierungen werden mit Ihren Einstellungen gespeichert, und ein erledigter Eintrag verlässt das Panel' },
          { label: 'Öffnen', text: 'Öffnen führt zur Seite des Eintrags; im Panel wird nichts genehmigt oder wiederholt' },
        ]
      },
    ],
    tips: [
      'Ihre angehefteten Module folgen Ihnen in jeden Browser und auf jedes Gerät, mit dem Sie sich anmelden',
      'Eine angeheftete Seite, die Sie nicht mehr öffnen dürfen, wird ausgeblendet und kehrt zurück, wenn die Berechtigung wiederhergestellt wird, bevor Sie Ihre Anheftungen ändern',
    ],
  },
}
