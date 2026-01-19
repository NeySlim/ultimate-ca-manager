'use client';
'use strict';

var react = require('react');
var context = require('../context.cjs');

function useModals() {
  const ctx = react.useContext(context.ModalsContext);
  if (!ctx) {
    throw new Error(
      "[@mantine/modals] useModals hook was called outside of context, wrap your app with ModalsProvider component"
    );
  }
  return ctx;
}

exports.useModals = useModals;
//# sourceMappingURL=use-modals.cjs.map
