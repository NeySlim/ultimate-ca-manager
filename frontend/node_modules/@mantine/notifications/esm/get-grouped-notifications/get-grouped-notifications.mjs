'use client';
const positions = [
  "bottom-center",
  "bottom-left",
  "bottom-right",
  "top-center",
  "top-left",
  "top-right"
];
function getGroupedNotifications(notifications, defaultPosition) {
  return notifications.reduce(
    (acc, notification) => {
      acc[notification.position || defaultPosition].push(notification);
      return acc;
    },
    positions.reduce((acc, item) => {
      acc[item] = [];
      return acc;
    }, {})
  );
}

export { getGroupedNotifications, positions };
//# sourceMappingURL=get-grouped-notifications.mjs.map
