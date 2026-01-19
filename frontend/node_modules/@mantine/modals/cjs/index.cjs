'use strict';

var ModalsProvider = require('./ModalsProvider.cjs');
var useModals = require('./use-modals/use-modals.cjs');
var events = require('./events.cjs');



exports.ModalsProvider = ModalsProvider.ModalsProvider;
exports.useModals = useModals.useModals;
exports.closeAllModals = events.closeAllModals;
exports.closeModal = events.closeModal;
exports.modals = events.modals;
exports.openConfirmModal = events.openConfirmModal;
exports.openContextModal = events.openContextModal;
exports.openModal = events.openModal;
exports.updateContextModal = events.updateContextModal;
exports.updateModal = events.updateModal;
//# sourceMappingURL=index.cjs.map
