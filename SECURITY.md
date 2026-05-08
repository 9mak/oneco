# セキュリティポリシー

## 脆弱性の報告

セキュリティ上の問題を発見された場合は、**公開 Issue を立てずに**以下の方法で報告してください。

- GitHub Security Advisories: https://github.com/9mak/oneco/security/advisories/new
- メール: 9mak.1112114853 [at] gmail.com（連絡先記載でやり取り）

報告いただいた内容は数日以内に確認し、影響範囲と修正方針を返信します。
緊急性が高い場合（認証バイパス・データ漏洩等）は当日対応します。

## サポートしているバージョン

`main` ブランチが常に最新で、セキュリティ修正は main に直接適用します。
リリースタグはまだ運用していません。

## 既知の運用上の注意

- `INTERNAL_API_TOKEN` は `/admin/stats` `PATCH /animals/{id}/status` 等の内部 API を保護します。漏洩した場合は速やかにローテーションしてください。
- `AUTH_GITHUB_*` `AUTH_SECRET` は管理ダッシュボード（/admin）の認証に使われます。漏洩時は GitHub OAuth App の Client Secret を再発行してください。
- 環境変数の保管場所は [`CLAUDE.md`](CLAUDE.md) のシークレット運用ルールに従い、shell rc への直書きを避けてください。
