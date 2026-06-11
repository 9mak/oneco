# AI-DLC and Spec-Driven Development

Kiro-style Spec Driven Development implementation on AI-DLC (AI Development Life Cycle)

## Project Context

### Paths
- Steering: `.kiro/steering/`
- Specs: `.kiro/specs/`

### Steering vs Specification

**Steering** (`.kiro/steering/`) - Guide AI with project-wide rules and context
**Specs** (`.kiro/specs/`) - Formalize development process for individual features

### Active Specifications
- Check `.kiro/specs/` for active specifications
- Use `/kiro:spec-status [feature-name]` to check progress

## Development Guidelines
- Think in English, generate responses in Japanese. All Markdown content written to project files (e.g., requirements.md, design.md, tasks.md, research.md, validation reports) MUST be written in the target language configured for this specification (see spec.json.language).

## Minimal Workflow
- Phase 0 (optional): `/kiro:steering`, `/kiro:steering-custom`
- Phase 1 (Specification):
  - `/kiro:spec-init "description"`
  - `/kiro:spec-requirements {feature}`
  - `/kiro:validate-gap {feature}` (optional: for existing codebase)
  - `/kiro:spec-design {feature} [-y]`
  - `/kiro:validate-design {feature}` (optional: design review)
  - `/kiro:spec-tasks {feature} [-y]`
- Phase 2 (Implementation): `/kiro:spec-impl {feature} [tasks]`
  - `/kiro:validate-impl {feature}` (optional: after implementation)
- Progress check: `/kiro:spec-status {feature}` (use anytime)

## Development Rules
- 3-phase approval workflow: Requirements → Design → Tasks → Implementation
- Human review required each phase; use `-y` only for intentional fast-track
- Keep steering current and verify alignment with `/kiro:spec-status`
- Follow the user's instructions precisely, and within that scope act autonomously: gather the necessary context and complete the requested work end-to-end in this run, asking questions only when essential information is missing or the instructions are critically ambiguous.

## Repository-specific Rules (避けたい再発バグ)

### Animal / 個体識別フィールドを触る変更
過去 6 回連続で `breed/name/management_number/description` のサイレントドロップを踏んだ (PR #171/#173/#176/#177/#180)。`Animal` / `RawAnimalData` / `AnimalData` / `AnimalArchive` のいずれかを変更する PR は `.github/pull_request_template.md` のチェックリストに必ず従うこと。最重要は:

1. **新規 adapter テストは `adapter.normalize(raw)` の戻り値 `AnimalData` でアサーションする** (`raw.breed == "..."` だけは不十分。模範: `tests/adapters/test_kochi_adapter.py::test_full_scraping_flow`)
2. **`Animal` に新カラム追加時は `AnimalArchive` も同時に追加する** (active から消えたら取り戻せないため、後付け移行不可)
3. **adapter で `normalize()` を override したら、RawAnimalData 再構築時に全フィールドを名前付き引数で明示的に引き継ぐ** (可能なら `_default_normalize` 委譲)

### CI が強制するチェック
- `tests/test_image_remote_patterns.py`: `sites.yaml` のホストが `frontend/next.config.ts` の `remotePatterns` に一致することを担保 (列挙漏れで silent failure 経験あり、PR #179)
- `ruff check src/ tests/` + `ruff format --check src/ tests/`: 個別ファイル単位の format 確認だけでは不十分。**全体で format 通っているか必ず確認** (PR #177/#178 でCI落ち再発)

## Steering Configuration
- Load entire `.kiro/steering/` as project memory
- Default files: `product.md`, `tech.md`, `structure.md`
- Custom files are supported (managed via `/kiro:steering-custom`)
