/**
 * 🧪 COLOR FOUNDATION TEST
 */

import { colors, getCSSVariables, colorCount } from '../colors.js';

console.log('📊 Color Count:', colorCount.total, colorCount.total === 262 ? '✅' : '❌');
console.log('🎨 Dark vars:', Object.keys(getCSSVariables('dark')).length);
console.log('🎨 Light vars:', Object.keys(getCSSVariables('light')).length);

const hexRegex = /^#[0-9A-Fa-f]{6}$/;
let invalidColors = [];
['dark', 'light'].forEach(theme => {
  Object.entries(colors[theme]).forEach(([key, value]) => {
    if (!hexRegex.test(value)) invalidColors.push(`${theme}.${key}`);
  });
});
console.log('🔍 Hex validation:', invalidColors.length === 0 ? '✅' : `❌ ${invalidColors.length} invalid`);

const darkKeys = Object.keys(colors.dark).sort();
const lightKeys = Object.keys(colors.light).sort();
const symmetric = JSON.stringify(darkKeys) === JSON.stringify(lightKeys);
console.log('🔄 Symmetry:', symmetric ? '✅' : '❌');

console.log('\n✨ RESULT:', colorCount.total === 262 && invalidColors.length === 0 && symmetric ? 'ALL PASSED ✅' : 'FAILED ❌');
