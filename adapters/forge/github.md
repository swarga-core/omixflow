---
port: forge
name: github
capabilities: [current_user, pr_create, pr_get, pr_files, pr_reviews, pr_threads, review_publish, reply, permalink]
requires:
  tools: []
  bin: [gh, jq, python3]
scripts: {}
---

# Адаптер forge: GitHub

Через `gh` CLI с авторизацией и scope `repo`. Скрипты сборки payload, валидации
hunks и выборки тредов появятся вместе со скилом ревью и будут объявлены в `scripts`.

## current_user

`gh api user --jq '{login, name}'`.

## pr_create

`git push -u origin {branch}`, затем `gh pr create --base {base} --title … --body …`.
Тело из артефактов задачи, не выдумывается. Если `gh` не авторизован, вернуть
инструкцию по настройке, не ошибку пайплайна.

## pr_get

`gh pr view {n} --json number,title,headRefName,headRefOid,baseRefName,author,state,body`.
Репозиторий определяется из remote, если передан только номер.

## pr_files

`gh api repos/{owner}/{repo}/pulls/{n}/files --paginate` с полем `patch`; валидные
строки для inline это добавленные и контекстные строки правой стороны.

## pr_reviews

`gh api repos/{owner}/{repo}/pulls/{n}/reviews --paginate`. **Каждый ответ в тред
GitHub возвращает здесь отдельной записью `state: COMMENTED` с пустым телом.**
Раунды и SHA предыдущего ревью считать только по записям текущего пользователя
с непустым `body`. Не класть вывод в переменную оболочки: многострочный markdown
ломает разбор; фильтровать одним вызовом через `--jq`.

## pr_threads

GraphQL `reviewThreads` с `isResolved`, `isOutdated`, комментариями и их
`databaseId`. REST не отдаёт resolved.

## review_publish

`gh api -X POST repos/{owner}/{repo}/pulls/{n}/reviews --input payload.json`
с `commit_id`, `body`, `event`, `comments[]`. Ответ в тред (`in_reply_to`) в этом
запросе не работает: ответы идут через `reply`.

## reply

`gh api -X POST repos/{owner}/{repo}/pulls/{n}/comments -f body=… -F in_reply_to={id}`,
последовательно, с остановкой на первой ошибке; при частичном сбое проверить,
не опубликован ли уже ответ, прежде чем повторять.

## permalink

`https://github.com/{owner}/{repo}/blob/{sha}/{path}#L{line}` или `#L{a}-L{b}`.
Всегда с SHA, не с именем ветки.
