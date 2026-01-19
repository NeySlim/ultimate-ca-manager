'use client';
import { randomId } from '@mantine/hooks';
import { createStore, useStore } from '@mantine/store';

function getDistributedNotifications(data, defaultPosition, limit) {
  const queue = [];
  const notifications2 = [];
  const count = {};
  for (const item of data) {
    const position = item.position || defaultPosition;
    count[position] = count[position] || 0;
    count[position] += 1;
    if (count[position] <= limit) {
      notifications2.push(item);
    } else {
      queue.push(item);
    }
  }
  return { notifications: notifications2, queue };
}
const createNotificationsStore = () => createStore({
  notifications: [],
  queue: [],
  defaultPosition: "bottom-right",
  limit: 5
});
const notificationsStore = createNotificationsStore();
const useNotifications = (store = notificationsStore) => useStore(store);
function updateNotificationsState(store, update) {
  const state = store.getState();
  const notifications2 = update([...state.notifications, ...state.queue]);
  const updated = getDistributedNotifications(notifications2, state.defaultPosition, state.limit);
  store.setState({
    notifications: updated.notifications,
    queue: updated.queue,
    limit: state.limit,
    defaultPosition: state.defaultPosition
  });
}
function showNotification(notification, store = notificationsStore) {
  const id = notification.id || randomId();
  updateNotificationsState(store, (notifications2) => {
    if (notification.id && notifications2.some((n) => n.id === notification.id)) {
      return notifications2;
    }
    return [...notifications2, { ...notification, id }];
  });
  return id;
}
function hideNotification(id, store = notificationsStore) {
  updateNotificationsState(
    store,
    (notifications2) => notifications2.filter((notification) => {
      if (notification.id === id) {
        notification.onClose?.(notification);
        return false;
      }
      return true;
    })
  );
  return id;
}
function updateNotification(notification, store = notificationsStore) {
  updateNotificationsState(
    store,
    (notifications2) => notifications2.map((item) => {
      if (item.id === notification.id) {
        return { ...item, ...notification };
      }
      return item;
    })
  );
  return notification.id;
}
function cleanNotifications(store = notificationsStore) {
  updateNotificationsState(store, () => []);
}
function cleanNotificationsQueue(store = notificationsStore) {
  updateNotificationsState(
    store,
    (notifications2) => notifications2.slice(0, store.getState().limit)
  );
}
const notifications = {
  show: showNotification,
  hide: hideNotification,
  update: updateNotification,
  clean: cleanNotifications,
  cleanQueue: cleanNotificationsQueue,
  updateState: updateNotificationsState
};

export { cleanNotifications, cleanNotificationsQueue, createNotificationsStore, hideNotification, notifications, notificationsStore, showNotification, updateNotification, updateNotificationsState, useNotifications };
//# sourceMappingURL=notifications.store.mjs.map
