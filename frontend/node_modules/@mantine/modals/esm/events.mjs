'use client';
import { createUseExternalEvents } from '@mantine/core';
import { randomId } from '@mantine/hooks';

const [useModalsEvents, createEvent] = createUseExternalEvents("mantine-modals");
const openModal = (payload) => {
  const id = payload.modalId || randomId();
  createEvent("openModal")({ ...payload, modalId: id });
  return id;
};
const openConfirmModal = (payload) => {
  const id = payload.modalId || randomId();
  createEvent("openConfirmModal")({ ...payload, modalId: id });
  return id;
};
const openContextModal = (payload) => {
  const id = payload.modalId || randomId();
  createEvent("openContextModal")({ ...payload, modalId: id });
  return id;
};
const closeModal = createEvent("closeModal");
const closeAllModals = createEvent("closeAllModals");
const updateModal = (payload) => createEvent("updateModal")(payload);
const updateContextModal = (payload) => createEvent("updateContextModal")(payload);
const modals = {
  open: openModal,
  close: closeModal,
  closeAll: closeAllModals,
  openConfirmModal,
  openContextModal,
  updateModal,
  updateContextModal
};

export { closeAllModals, closeModal, createEvent, modals, openConfirmModal, openContextModal, openModal, updateContextModal, updateModal, useModalsEvents };
//# sourceMappingURL=events.mjs.map
