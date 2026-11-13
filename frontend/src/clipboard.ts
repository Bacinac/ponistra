/** What the clipboard holds: its text, or the images on it when it holds no text. */
export async function clipboardHeld(): Promise<{ text: string; files: File[] }> {
  const items = await navigator.clipboard.read();
  for (const item of items)
    if (item.types.includes('text/plain'))
      return { text: await (await item.getType('text/plain')).text(), files: [] };
  const files: File[] = [];
  for (const item of items)
    for (const type of item.types)
      if (type.startsWith('image/'))
        files.push(new File([await item.getType(type)], `pasted.${type.slice(6)}`, { type }));
  return { text: '', files };
}

/** Puts a text where the field's caret stands, over what it has selected, as typing it would. */
export function typedInto(field: HTMLTextAreaElement | HTMLInputElement, text: string) {
  field.focus();
  field.setRangeText(text, field.selectionStart ?? 0, field.selectionEnd ?? 0, 'end');
  // React hears the change through the input event, the value having bypassed its setter.
  field.dispatchEvent(new Event('input', { bubbles: true }));
}
