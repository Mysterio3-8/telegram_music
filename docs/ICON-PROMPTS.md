# Промты для генерации иконок и фонов TG Music

**Удобная версия с кнопками «Копировать»:**
https://claude.ai/code/artifact/c5245fd3-f577-4254-b243-5bf9f1858341
(копирует готовый промт целиком — блок стиля подставляется сам)

Ниже — тот же материал текстом, на случай если ссылка недоступна.

Как пользоваться: **блок стиля ниже вставляется в начало каждого промта**, к нему
добавляется строка конкретной иконки. Один и тот же блок стиля — залог того, что
30 иконок будут выглядеть одним набором, а не солянкой.

Формат результата: **SVG**, если генератор умеет; иначе PNG 512×512 на прозрачном фоне.

---

## Блок стиля (копировать в каждый промт)

```
Minimalist line icon for a dark-themed music app, 24x24 grid, 2px uniform stroke
weight, rounded line caps and joins, no fill, single color (pure white on
transparent background), geometric and balanced, generous negative space,
optically centered, no gradients, no shadows, no text, no background shape,
flat vector, consistent with a modern iOS/Material icon set.
Icon subject:
```

## Навигация и оболочка

| Иконка | Строка субъекта |
|---|---|
| Главная | `a house with a simple pitched roof` |
| Поиск | `a magnifying glass tilted 45 degrees` |
| Библиотека | `three vertical books or a stack of media cards` |
| Профиль | `a person bust silhouette in outline` |
| Настройки | `a gear with six teeth` |
| Назад | `a left-pointing chevron` |
| Закрыть | `an X cross` |
| Ещё | `three horizontal dots in a row` |

## Плеер

| Иконка | Строка субъекта |
|---|---|
| Играть | `a right-pointing triangle play symbol` |
| Пауза | `two vertical parallel bars` |
| Следующий | `a right-pointing triangle with a vertical bar on its right` |
| Предыдущий | `a left-pointing triangle with a vertical bar on its left` |
| Перемешать | `two crossing arrows shuffling` |
| Повтор | `two arrows forming a closed loop rectangle` |
| Повтор трека | `two arrows forming a closed loop with the numeral 1 inside` |
| Очередь | `three stacked horizontal lines with a small play triangle at the left` |
| Таймер сна | `a crescent moon next to a small clock` |
| Громкость | `a speaker with two curved sound waves` |
| Эквалайзер | `three vertical sliders at different heights` |
| Текст песни | `a speech quote mark above three text lines` |
| Караоке | `a handheld microphone with a rounded head` |

## Действия с треком

| Иконка | Строка субъекта |
|---|---|
| В избранное | `a heart outline` |
| В избранном | `a solid filled heart` |
| Добавить | `a plus sign inside a circle` |
| Добавлено | `a checkmark inside a circle` |
| В плейлист | `three stacked lines with a plus sign at the right` |
| Сохранить офлайн | `a downward arrow into an open tray` |
| Сохранено офлайн | `a downward arrow into a tray with a small checkmark` |
| Поделиться | `three connected dots forming a share node graph` |
| Скрыть трек | `a crossed-out eye` |

## Каталог

| Иконка | Строка субъекта |
|---|---|
| Плейлист | `three horizontal lines with a musical note at the right` |
| Альбом | `a vinyl record disc with a center hole` |
| Артист | `a person bust with a small microphone` |
| Жанр | `a musical note inside a rounded square tag` |
| Микс | `two interleaving wave lines forming a braid` |
| Новинки | `a four-pointed sparkle star` |
| Минусы | `a musical note with a small minus badge` |
| Импорт трека | `an arrow curving down into a music note` |
| Перенос музыки | `two arrows exchanging between two rounded squares` |

## Рост и монетизация

| Иконка | Строка субъекта |
|---|---|
| Premium | `a five-point crown with a small gem in the center` |
| Достижения | `a rounded award medal with a ribbon` |
| Рефералы | `two person silhouettes with a plus sign` |
| Конкурс | `a gift box with a ribbon cross on top` |
| Итоги года | `a calendar page with a star in the middle` |
| Друзья | `three overlapping person silhouettes` |
| Аккаунт артиста | `a verified checkmark badge with rounded scalloped edge` |

---

## Фоны

Фоны — крупные, размытые, **без деталей и без текста**: поверх них ложится интерфейс,
и мелкий рисунок будет мешать читаемости.

**Главная (hero-микс):**
```
Abstract dark background for a music app hero banner, deep charcoal base (#0f0f10)
with a soft diffused gradient glow of electric blue and magenta bleeding from the
lower left, heavy gaussian blur, subtle film grain texture, no objects, no text,
no people, smooth and atmospheric, 1080x1080, high quality.
```

**Premium:**
```
Abstract luxury dark background, near-black base with a slow sweeping gradient of
deep violet and warm gold, soft bokeh light bloom in the upper right, fine grain,
no objects, no text, premium and restrained, 1080x1080.
```

**Экран конкурса:**
```
Abstract festive dark background, near-black base with soft confetti-like bokeh
particles in blue and pink, strongly blurred and low contrast so interface text
stays readable, no text, no objects, 1080x1080.
```

**Заглушка обложки трека** (когда обложки нет):
```
Abstract square album art placeholder, dark charcoal base with a smooth diagonal
gradient of muted blue to muted purple, very soft geometric wave shapes, no text,
no logo, minimal and neutral, 1000x1000.
```

---

## Что прислать обратно

Папкой, имена файлов — по названию иконки латиницей: `home.svg`, `search.svg`,
`play.svg`, `heart.svg`, `crown.svg` и т.д. Фоны — `bg-home.jpg`, `bg-premium.jpg`,
`bg-contest.jpg`, `cover-placeholder.jpg`.

До получения файлов интерфейс работает на встроенном SVG-наборе — работа не стоит.
