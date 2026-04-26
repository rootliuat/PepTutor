export function stripLessonMarkdown(text: string): string {
  return text
    .replace(/<\|ACT[\s\S]*?\|>/g, ' ')
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/`{1,3}([^`]+)`{1,3}/g, '$1')
    .replace(/(\*\*|__)(.*?)\1/g, '$2')
    .replace(/(^|[\s(])(\*|_)([^*_]+)\2(?=[\s).,!?:;，。！？；：]|$)/g, '$1$3')
    .replace(/~~(.*?)~~/g, '$1')
    .replace(/^[>\-+*#\s]+/gm, '')
    .replace(/\s+/g, ' ')
    .trim()
}
