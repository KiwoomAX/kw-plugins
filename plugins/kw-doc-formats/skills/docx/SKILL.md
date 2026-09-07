---
name: docx
description: 워드 문서(.docx)를 만들거나 읽을 때 document-skills:docx와 함께 반드시 연다. 공식 스킬이 쓰라는 npm docx 와 pandoc 은 이 PC에 없다. 여기서는 python-docx 로 만들고 markitdown 으로 읽는다.
---

# 워드 문서를 만들고 읽을 때

**`kw-doc-formats:common` 을 함께 본다.** 파일을 열고 쓸 때의 인코딩과, 어떤 형식이 바로
읽히는지가 거기 있다.

일반적인 워드 문서 다루기는 `document-skills:docx` 에 있다. 여기는 이 PC에서 그 기본값이 틀리거나
그 도구가 없는 자리만 적는다.

## 이 PC에서는 python-docx 로 만들고 markitdown 으로 읽는다

공식 `document-skills:docx` 는 만들 때 npm `docx` 를, 읽을 때 `pandoc` 을 쓰라고 한다.
**이 PC에는 둘 다 없다.** 설치기가 깔아 주는 것은 `python-docx` 와 `markitdown` 이므로
그 둘을 쓴다.

```python
import docx                        # 만들 때
d = docx.Document()
d.add_paragraph("보고서 본문")
d.save("보고서.docx")
```

```
python -m markitdown 보고서.docx    # 읽을 때
```

공식 스킬의 나머지 조언은 그대로 쓸 수 있다. 변경 추적과 주석과 `document.xml` 을 직접
고치는 방법이 거기 있다. 도구를 고르는 자리만 다르다.

## 아직 재지 않은 것

`python-docx` 1.2.0 이 만드는 빈 문서를 열어 보면 테마의 로마자 글꼴 슬롯이 Calibri 이고
동아시아 슬롯이 비어 있으며, 스타일 기본값의 언어 태그가 동아시아까지 `en-US` 다. 발표자료에서
같은 종류의 기본값이 한글을 상하게 하는 것을 실측했으므로 워드에서도 그럴 수 있다.

**다만 그것이 실제로 어떻게 보이는지는 아직 재지 않았다.** 이 문서를 쓴 PC에 워드가 없어
만든 문서를 열어 견줄 수 없었다. 워드가 있는 PC에서 한글이 든 문서를 만들어 열고, 슬롯을
채운 것과 안 채운 것을 나란히 놓고 본 뒤에 규칙을 적는다. 그 전에는 짐작으로 적지 않는다.
