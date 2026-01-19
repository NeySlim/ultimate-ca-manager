'use client';
'use strict';

var core = require('@mantine/core');
var hooks = require('@mantine/hooks');

const [useModalsEvents, createEvent] = core.createUseExternalEvents("mantine-modals");
const openModal = (payload) => {
  const id = payload.modalId || hooks.randomId();
  createEvent("openModal")({ ...payload, modalId: id });
  return id;
};
const openConfirmModal = (payload) => {
  const id = payload.modalId || hooks.randomId();
  createEvent("openConfirmModal")({ ...payload, modalId: id });
  return id;
};
const openContextModal = (payload) => {
  const id = payload.modalId || hooks.randomId();
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

exports.closeAllModals = closeAllModals;
exports.closeModal = closeModal;
exports.createEvent = createEvent;
exports.modals = modals;
exports.openConfirmModal = openConfirmModal;
exports.openContextModal = openContextModal;
exports.openModal = openModal;
exports.updateContextModal = updateContextModal;
exports.updateModal = updateModal;
exports.useModalsEvents = useModalsEvents;
//# sourceMappingURL=events.cjs.map
