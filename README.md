# AI Translation & QA Review — Claude plugin

Translation and translation-QA pipeline for Claude (Cowork / Claude Code): TEP with
independent four-eyes review, MQM scoring, deterministic tag/placeholder checks,
Trados SDLXLIFF and Phrase MXLIFF round-trip, back-translation, provenance check
(human vs MT), and a cross-job TM/termbase.

---

## งานที่ทำได้

| โหมด | ใช้เมื่อ | ตัวอย่างคำสั่ง |
|---|---|---|
| A — แปล + QA | มีต้นฉบับอย่างเดียว | "แปลไฟล์นี้เป็นไทย ระดับส่งลูกค้า" |
| A — redline update | แก้เฉพาะส่วนที่เปลี่ยนจากฉบับที่ตีพิมพ์แล้ว | "แปลเฉพาะข้อความสีแดง อ้างอิงฉบับเดิม" |
| B — ตรวจงานแปล | มีต้นฉบับ + คำแปลของคนอื่น (หรือไฟล์ SDLXLIFF/MXLIFF) | "ตรวจไฟล์ sdlxliff นี้ ขอ QA report" |
| C — ตรวจไฟล์ prep | มีไฟล์ที่ถอดข้อความมา + artwork/PDF ต้นฉบับ | "เช็คไฟล์ prep เทียบกับ artwork" |
| D — provenance | อยากรู้ว่างานแปลนี้คนแปลหรือ MT/AI | "งานนี้ vendor ใช้ MT หรือเปล่า" |

พิมพ์คำสั่งเป็นภาษาปกติได้เลย ถ้า skill ไม่ทำงานขึ้นมาเอง ให้เรียกชื่อ skill `ai-translation-qa`
ตรง ๆ (ใน Claude Code พิมพ์ `/ai-translation-qa:ai-translation-qa`)

## ติดตั้ง

**ก่อนติดตั้ง:** ใน Settings → Capabilities เปิด **Code execution and file creation** และ
**Skills** ถ้าปิดอยู่ skill จะไม่ทำงานเลย

**Cowork (Claude Desktop):** ไปที่หน้า Plugins → เพิ่ม marketplace จาก GitHub repository →
ใส่ `Jirawatpyk/ai-translation-qa` → ติดตั้ง plugin **ai-translation-qa**

**Claude Code:**

```
/plugin marketplace add Jirawatpyk/ai-translation-qa
/plugin install ai-translation-qa@jirawatpyk-tools
```

ห้ามอัปโหลด skill ตัวเดียวกันแยกเป็นไฟล์ `.skill` / `.zip` ซ้ำอีกชุด เพราะจะมีสองชุดแย่งกันทำงาน
และชุดที่อัปโหลดเองจะไม่ได้รับอัปเดต

## อัปเดต

แต่ละรุ่นมีบันทึกอยู่ใน [CHANGELOG.md](CHANGELOG.md)

- **Cowork:** กด Update ที่ marketplace หรือที่ plugin
- **Claude Code:** `/plugin marketplace update`

## วิธีใช้ให้ได้ผล

1. **รันใน Cowork ไม่ใช่หน้า chat ธรรมดา** การตรวจแบบ four-eyes (คนแปล คนตรวจ และคนพิสูจน์อักษร
   แยก context กันจริง) ต้องใช้ sub-agent ถ้ารันในหน้า chat ธรรมดา skill จะตรวจแบบจำลองแทน
   และเขียนระบุไว้ในรายงาน
2. **เริ่มทุกงานจาก Project เดียวกัน** ให้สร้าง Project หนึ่งอันไว้ใน account (เช่น `QA — TM`)
   TM และ termbase ของลูกค้าแต่ละรายจะถูกเก็บไว้ใน Project นั้น โดยแยกไฟล์ตามลูกค้า + คู่ภาษา
   (`tm-<ลูกค้า>-<คู่ภาษา>.jsonl`, `termbase-<ลูกค้า>-<คู่ภาษา>.jsonl`)
   - ไฟล์เริ่มสร้างหลังส่งมอบงานแรก และจะใช้ได้มากขึ้นเรื่อย ๆ ตามจำนวนงาน
   - คำที่ลูกค้ายืนยันแล้วเท่านั้นที่ขึ้นสถานะ confirmed
3. **อย่าเปิดงานของลูกค้า + คู่ภาษาเดียวกันพร้อมกันสองงาน** ถ้าสองงานเขียน TM ไฟล์เดียวกันพร้อมกัน
   ข้อมูลบางส่วนอาจหาย ส่วนงานของต่างลูกค้าหรือต่างคู่ภาษา เปิดพร้อมกันได้
4. **ไฟล์ CAT ที่ skill เขียนกลับมา** (SDLXLIFF/MXLIFF) ให้เปิดใน Trados/Phrase แล้วรัน QA
   ในโปรแกรมนั้นก่อนส่งลูกค้า โดยเฉพาะ segment ที่มีแท็ก ส่วน segment ที่ skill ไม่ยอมเขียน
   จะมีรายการพร้อมเหตุผลอยู่ใน QA report ให้ไปแก้เองใน CAT tool
5. **Thai target:** skill จะติดตั้ง `pythainlp` เองเพื่อตรวจการตัดคำ ถ้าติดตั้งไม่ได้
   (เพราะไม่มี network) การเช็คตัดคำไทยจะถูกข้ามไป และรายงานจะระบุไว้

## ข้อห้าม

repo นี้เป็น **public** ห้ามนำไฟล์ต่อไปนี้ขึ้นมาเด็ดขาด:

- ไฟล์ลูกค้า
- TM / termbase
- QA report
- ชื่อลูกค้าหรือเลขงาน

`.gitignore` กันไฟล์ประเภทพวกนี้ไว้ระดับหนึ่งแล้ว แต่ความรับผิดชอบยังอยู่ที่คน commit

---

## For the maintainer — release flow

```
plugins/ai-translation-qa/
  .claude-plugin/plugin.json        ← version
  skills/ai-translation-qa/         ← SKILL.md, references/, scripts/
.claude-plugin/marketplace.json     ← version (must match)
tests/                              ← synthetic TP/FP tests (not shipped)
tools/release_check.py              ← pre-release gate
```

1. Edit the skill under `plugins/ai-translation-qa/skills/ai-translation-qa/`.
2. Bump `version` in **both** manifests and add a `CHANGELOG.md` entry. Without the
   bump, no user receives the release.
3. `python3 tools/release_check.py`. It checks version sync, description length, junk
   and client-data files, the local `.trace-denylist` (gitignored: client/vendor names,
   one per line), and runs the tests.
4. Commit, push to `main`, and tell the team to press Update.
