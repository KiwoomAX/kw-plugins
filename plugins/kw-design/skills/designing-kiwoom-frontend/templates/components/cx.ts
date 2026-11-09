/* 조건에 맞는 클래스 이름만 이어 붙인다. */
export function cx(...names: Array<string | false | undefined>): string {
  return names.filter(Boolean).join(' ');
}
