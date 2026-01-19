'use client';
'use strict';

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

exports.getGroupedNotifications = getGroupedNotifications;
exports.positions = positions;
//# sourceMappingURL=get-grouped-notifications.cjs.map
