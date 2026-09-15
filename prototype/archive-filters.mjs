// Search record metadata and filenames, never infer content from an unknown format.
export function filterRecords(records, filters = {}) {
  const tokens = (filters.query || '').toLowerCase().trim().split(/\s+/).filter(Boolean);
  const category = (filters.category || '').toLowerCase().trim();
  if (filters.from && filters.to && filters.from > filters.to) {
    throw Error('The start date must not be after the end date.');
  }
  const selected = records.filter(record => {
    const materials = record.materials || [];
    const text = [record.title, record.category, record.notes, ...(record.tags || []), ...materials.map(m => m.name)].join(' ').toLowerCase();
    if (!tokens.every(token => text.includes(token))) return false;
    if (category && (record.category || '').toLowerCase() !== category) return false;
    if (filters.kind && !materials.some(m => m.kind === filters.kind)) return false;
    if (filters.unknown) return !record.date;
    if (filters.from && (!record.date || record.date < filters.from)) return false;
    if (filters.to && (!record.date || record.date > filters.to)) return false;
    return true;
  });
  return selected.sort((a, b) => {
    if (filters.sort === 'title') return a.title.localeCompare(b.title);
    if (filters.sort === 'date-newest' || filters.sort === 'date-oldest') {
      if (!a.date !== !b.date) return a.date ? -1 : 1;
      const order = (a.date || '').localeCompare(b.date || '');
      if (order) return filters.sort === 'date-oldest' ? order : -order;
    }
    return (b.savedAt || '').localeCompare(a.savedAt || '') || a.title.localeCompare(b.title);
  });
}
