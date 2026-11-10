export default {
  helpContent: {
    title: 'Overview',
    subtitle: 'What needs action, and the state of the PKI',
    overview: 'Six independent cards over the live data of your PKI. Each card loads on its own and shows its own loading, empty, error or missing-permission state. Every counter that has a list opens the certificate list filtered to exactly the certificates it counts.',
    sections: [
      {
        title: 'Cards',
        items: [
          { label: 'To handle', text: 'The six most urgent items, critical first, each linking to its record; a folded tier gives the total per kind, and the four renewal kinds open the certificate list' },
          { label: 'Automation health', text: 'Per protocol (ACME, SCEP, EST) the daily successes and failures, and the scheduler state' },
          { label: 'Hierarchy', text: 'The authorities as a tree under their parent, with CRL and OCSP state, an offline or cross-signed mark, and the certificates each issued over 7 days; each authority opens its page' },
          { label: 'Expiry horizon', text: 'The expiring and expired counters, each opening its list, and the five certificates that expire next' },
          { label: 'Compliance', text: 'Live certificates by key algorithm and weakness (RSA below 3072 bits, weak signature hash, server certificates over 398 days, incomplete chain, no private key); each counter opens the matching list' },
          { label: 'Latest operations', text: 'The five most recent operations; with the audit permission, a link opens the whole trail' },
        ]
      },
    ],
    tips: [
      'Pick the Operator, Manager or All cards preset in the header to choose which cards are shown',
      'The layout is saved with your account and follows you across browsers',
      'On the certificate list, filters coming from the overview appear as chips; remove one with its x',
    ],
  },
  helpGuides: {
    title: 'Панель моніторингу',
    content: `
## Огляд

Панель моніторингу: це ваш центральний хаб моніторингу. Вона відображає метрики, графіки та сповіщення в реальному часі про всю вашу інфраструктуру PKI через налаштовувані віджети.

## Віджети

### Картка статистики
Відображає такі лічильники:
- **Сертифікати**: усі сертифікати, разом із простроченими та відкликаними
- **CA**: кореневі та проміжні центри сертифікації
- **CSR**: запити на підпис сертифікатів, що очікують підпису
- **ACME**: зареєстровані облікові записи ACME
- **SSH-сертифікати**: показуються, коли існує SSH CA

### Активність сертифікатів
Обласна діаграма виданих, відкликаних і прострочених сертифікатів за день у вибраному періоді. Наведіть курсор на точки даних, щоб побачити точні значення.

### Розподіл за статусом
Кругова діаграма, що показує розподіл станів сертифікатів:
- **Дійсний**: У межах періоду дійсності та не відкликаний
- **Закінчується**: Закінчується протягом 30 днів
- **Прострочений**: Минула дата «Не після»
- **Відкликаний**: Явно відкликаний

### Найближче закінчення
Перелік шести дійсних сертифікатів, що закінчуються найраніше, незалежно від дати. Натисніть на будь-який сертифікат, щоб перейти до його деталей.

### Стан системи
Показує стан служб UCM:
- Сервер ACME (увімкнено/вимкнено)
- Сервер SCEP
- Протокол EST (увімкнено/вимкнено, призначений CA)
- Автоматична регенерація CRL з кількістю CDP
- Відповідач OCSP
- TSA, SMTP і вебхуки
- Стан автоматичного оновлення

Панель «Стан системи» також показує з'єднання WebSocket, базу даних, API та час останнього оновлення.

### Остання активність
Стрічка останніх операцій у реальному часі: видача сертифікатів, відкликання, імпорт, входи користувачів. Оновлюється в реальному часі через WebSocket.

### Центри сертифікації
Швидкий перегляд останніх CA, кожен позначений як Root або Sub.

### Закінчення довіреного сховища
Довірені сертифікати, що закінчуються найраніше.

### Облікові записи ACME
Перелік зареєстрованих облікових записів клієнтів ACME та кількості їх замовлень.

## Налаштування

### Зміна розташування віджетів
Натисніть **«Редагувати макет»** у заголовку сторінки, потім перетягніть будь-який віджет за його заголовок, щоб змінити його позицію. Макет використовує адаптивну сітку, що підлаштовується під розмір вашого екрана.

### Показ/Приховування віджетів
Натисніть **«Налаштувати панель»** (значок повзунків) у заголовку сторінки, потім око біля віджета, щоб переключити його видимість. Приховані віджети запам'ятовуються між сеансами.

### Збереження макета
Макет зберігається в браузері, а не в обліковому записі: його спільно використовують усі облікові записи, що входять із того самого профілю браузера, а інший браузер починає зі стандартного макета.

## Оновлення в реальному часі
Панель отримує оновлення в реальному часі через WebSocket. Ручне оновлення не потрібне: нові сертифікати, зміни статусу та записи активності з'являються автоматично.

> 💡 Зелена крапка в бічній панелі показує активне з'єднання WebSocket і зникає, коли воно розривається. Дані оновляться при повторному підключенні.
`
  }
}
