using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Threading;
using Microsoft.Win32;

namespace Efren.Panel
{
    static class PageUI
    {
        public static TextBlock Text(string value, bool muted = false)
        {
            var text = new TextBlock { Text = value, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 4, 0, 8) };
            text.SetResourceReference(TextBlock.ForegroundProperty, muted ? "ThemeMuted" : "ThemeText"); return text;
        }
        public static TextBox Input(bool multiline = false)
        {
            var field = new TextBox { Padding = new Thickness(10), Margin = new Thickness(0, 0, 8, 8), AcceptsReturn = multiline, TextWrapping = TextWrapping.Wrap, VerticalScrollBarVisibility = ScrollBarVisibility.Auto };
            field.SetResourceReference(Control.BackgroundProperty, "ThemeButton"); field.SetResourceReference(Control.ForegroundProperty, "ThemeText");
            field.SetResourceReference(Control.BorderBrushProperty, "ThemeButtonBorder"); field.SetResourceReference(TextBox.CaretBrushProperty, "ThemeAccent"); return field;
        }
        public static Button Button(string label, Func<Task> action)
        {
            var button = new Button { Content = label };
            button.Click += async delegate {
                button.IsEnabled = false;
                try { await action(); } catch (Exception ex) { MessageBox.Show(Window.GetWindow(button), ex.Message, "Не удалось выполнить"); }
                finally { button.IsEnabled = true; }
            }; return button;
        }
        public static ComboBox Combo(IEnumerable<string> values)
        {
            return new ComboBox { ItemsSource = values, SelectedIndex = 0, MinWidth = 120, Margin = new Thickness(0, 0, 8, 8) };
        }
        public static object[] Array(object value) { return ((IEnumerable)value).Cast<object>().ToArray(); }
        public static string Str(Dictionary<string, object> d, string key) { return d.ContainsKey(key) ? Convert.ToString(d[key]) : ""; }
        public static bool Flag(Dictionary<string, object> d, string key) { return d.ContainsKey(key) && d[key] is bool && (bool)d[key]; }
    }

    sealed class JournalPage : UserControl
    {
        public Task RefreshPage() { output.Select(0, 0); return Read(false); }
        readonly Backend backend; readonly string source;
        readonly TextBox search = PageUI.Input(), output = PageUI.Input(true), input = PageUI.Input();
        readonly ComboBox period = PageUI.Combo(new[] { "Последние 5 минут", "Последние 15 минут", "Последние 30 минут", "Последний час", "Сегодня", "Вся история" });
        readonly ComboBox person = PageUI.Combo(new[] { "Все участники" });
        readonly ComboBox kind = PageUI.Combo(new[] { "Все события", "Обычный разговор", "Команды", "Ошибки" });
        readonly TextBlock status = PageUI.Text("Загрузка…", true), consoleStatus = PageUI.Text("", true);
        readonly DispatcherTimer timer = new DispatcherTimer();
        readonly WrapPanel favorites = new WrapPanel();
        string[] favoriteValues = new string[0];
        bool live = true, busy, sending;
        public JournalPage(Backend backend, string source, Action openReplies)
        {
            this.backend = backend; this.source = source;
            var grid = new Grid(); Content = grid;
            grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            grid.RowDefinitions.Add(new RowDefinition());
            grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            var top = new StackPanel(); grid.Children.Add(top);
            top.Children.Add(PageUI.Text("Поиск по тексту. История: до 100 000 последних событий / 64 МБ; показ до 1500 совпадений. Ctrl+C копирует выделенное.", true));
            top.Children.Add(search); search.MaxLength = 400;
            var filters = new WrapPanel(); top.Children.Add(filters); period.SelectedIndex = 1;
            filters.Children.Add(period);
            if (source == "friday") filters.Children.Add(person);
            filters.Children.Add(kind);
            filters.Children.Add(PageUI.Button("Найти", async delegate { live = false; output.Select(0, 0); await Read(false); }));
            filters.Children.Add(PageUI.Button("Живой журнал", async delegate { live = true; search.Clear(); output.Select(0, 0); await Read(false); }));
            filters.Children.Add(PageUI.Button("Скопировать контекст", async delegate { await Read(true); }));
            search.KeyDown += async delegate(object s, KeyEventArgs e) { if (e.Key == Key.Enter) { e.Handled = true; live = false; output.Select(0, 0); await Read(false); } };
            top.Children.Add(status);
            output.IsReadOnly = true; output.FontFamily = new FontFamily("Consolas"); output.FontSize = 12;
            output.HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled;
            Grid.SetRow(output, 1); grid.Children.Add(output);
            var bottom = new StackPanel(); Grid.SetRow(bottom, 2); grid.Children.Add(bottom);
            if (source == "friday") {
                bottom.Children.Add(PageUI.Text("Enter — команда · Ctrl+Enter — только озвучить", true));
                input.MaxLength = 400; bottom.Children.Add(input);
                var buttons = new WrapPanel(); bottom.Children.Add(buttons);
                buttons.Children.Add(PageUI.Button("Выполнить", async delegate { await Send("command"); }));
                buttons.Children.Add(PageUI.Button("Только озвучить", async delegate { await Send("speech"); }));
                buttons.Children.Add(PageUI.Button("★ Добавить в избранное", async delegate {
                    await backend.Call("favorite", "operation", "add", "text", input.Text); await LoadFavorites();
                    consoleStatus.Text = "Добавлено. Правый клик по избранной команде удаляет её.";
                }));
                buttons.Children.Add(PageUI.Button("Ответы", delegate { openReplies(); return Task.FromResult(0); }));
                bottom.Children.Add(new ScrollViewer { Content = favorites, MaxHeight = 85, VerticalScrollBarVisibility = ScrollBarVisibility.Auto });
                bottom.Children.Add(consoleStatus);
                input.PreviewKeyDown += async delegate(object s, KeyEventArgs e) {
                    if (e.Key == Key.Enter) { e.Handled = true; if (!e.IsRepeat) await Send((Keyboard.Modifiers & ModifierKeys.Control) != 0 ? "speech" : "command"); }
                };
            }
            timer.Interval = TimeSpan.FromSeconds(1);
            timer.Tick += async delegate { if (IsVisible && live && output.SelectionLength == 0) await Read(false); };
            IsVisibleChanged += async delegate { if (IsVisible) { timer.Start(); await Read(false); await LoadFavorites(); } else timer.Stop(); };
            Unloaded += delegate { timer.Stop(); };
        }
        async Task LoadFavorites()
        {
            if (source != "friday") return;
            try {
                var data = (Dictionary<string, object>)await backend.Call("journal_settings");
                var values = PageUI.Array(data["favorites"]).Select(Convert.ToString).Take(8).ToArray();
                if (favoriteValues.SequenceEqual(values)) return;
                favoriteValues = values; favorites.Children.Clear();
                foreach (string value in values) {
                    string command = value;
                    var button = PageUI.Button(command.Length > 35 ? command.Substring(0, 32) + "…" : command, async delegate {
                        if (sending) return; input.Text = command; await Send("command");
                    });
                    button.ToolTip = command + "\nНажатие — выполнить; правый клик — удалить";
                    button.PreviewMouseRightButtonUp += async delegate(object sender, MouseButtonEventArgs e) {
                        e.Handled = true;
                        try { await backend.Call("favorite", "operation", "remove", "text", command); await LoadFavorites(); }
                        catch (Exception ex) { consoleStatus.Text = ex.Message; }
                    };
                    favorites.Children.Add(button);
                }
            } catch (Exception ex) { consoleStatus.Text = "Избранное недоступно: " + ex.Message; }
        }
        async Task Send(string mode)
        {
            if (sending) return;
            sending = true; input.IsReadOnly = true;
            try { await backend.Call("console", "mode", mode, "text", input.Text); input.Clear(); consoleStatus.Text = "Запрос принят. Результат будет в журнале."; }
            catch (Exception ex) { consoleStatus.Text = ex.Message; }
            finally { sending = false; input.IsReadOnly = false; }
        }
        async Task Read(bool context)
        {
            if (busy) return;
            busy = true;
            try {
                var data = (Dictionary<string, object>)await backend.Call("logs", "source", source, "live", live && !context, "context", context,
                    "query", search.Text, "period", Convert.ToString(period.SelectedItem), "person", Convert.ToString(person.SelectedItem), "kind", Convert.ToString(kind.SelectedItem));
                string text = PageUI.Str(data, "text");
                if (context) { Clipboard.SetText(text.Length == 0 ? "Нет фраз по выбранным фильтрам." : text); status.Text = "Контекст скопирован."; return; }
                string selectedPerson = Convert.ToString(person.SelectedItem);
                var people = new[] { "Все участники" }.Concat(PageUI.Array(data["people"]).Select(Convert.ToString)).ToArray();
                if (!((IEnumerable<string>)person.ItemsSource).SequenceEqual(people)) { person.ItemsSource = people; person.SelectedItem = people.Contains(selectedPerson) ? selectedPerson : people[0]; }
                if (output.Text != text && output.SelectionLength == 0) {
                    double position = output.VerticalOffset;
                    bool tail = output.Text.Length == 0 || output.VerticalOffset + output.ViewportHeight >= output.ExtentHeight - 3;
                    output.Text = text;
                    if (live && tail) output.ScrollToEnd(); else output.ScrollToVerticalOffset(position);
                    if (!live && !String.IsNullOrWhiteSpace(search.Text)) {
                        int found = text.IndexOf(search.Text, StringComparison.CurrentCultureIgnoreCase);
                        if (found >= 0) { output.Select(found, search.Text.Length); output.Focus(); }
                    }
                }
                status.Text = (live ? "Живой журнал · " : "Найдено: " + data["count"] + " · ") + "Показано: " + data["shown"] + " · " + data["path"];
            } catch (Exception ex) { status.Text = "Ошибка чтения: " + ex.Message; }
            finally { busy = false; }
        }
    }

    sealed class CommandsPage : UserControl
    {
        readonly Backend backend;
        readonly StackPanel rows = new StackPanel();
        readonly TextBlock status = PageUI.Text("Загрузка…", true);
        bool busy;
        public CommandsPage(Backend backend)
        {
            this.backend = backend;
            var body = new DockPanel(); Content = body;
            var top = new StackPanel(); DockPanel.SetDock(top, Dock.Top); body.Children.Add(top);
            top.Children.Add(PageUI.Text("Здесь показаны настоящие голосовые привязки помощника. Отключение сохраняет сценарий; удаление убирает только голосовую фразу и не удаляет файл .jmacro.", true));
            top.Children.Add(PageUI.Button("Обновить список", Load)); top.Children.Add(status);
            body.Children.Add(new ScrollViewer { Content = rows, VerticalScrollBarVisibility = ScrollBarVisibility.Auto });
            IsVisibleChanged += async delegate { if (IsVisible) await Load(); };
        }
        public Task RefreshPage() { return Load(); }
        async Task Load()
        {
            if (busy) return; busy = true;
            try
            {
                var data = (Dictionary<string, object>)await backend.Call("macros", "operation", "registry");
                rows.Children.Clear(); int count = 0;
                foreach (var command in PageUI.Array(data["commands"]).Cast<Dictionary<string, object>>())
                {
                    count++;
                    string phrase = PageUI.Str(command, "phrase"), path = PageUI.Str(command, "path");
                    bool enabled = PageUI.Flag(command, "enabled"), exists = PageUI.Flag(command, "exists");
                    var card = new Border { Padding = new Thickness(14), Margin = new Thickness(0, 0, 0, 10), CornerRadius = new CornerRadius(10) };
                    card.SetResourceReference(Border.BackgroundProperty, "ThemeCard"); rows.Children.Add(card);
                    var content = new StackPanel(); card.Child = content;
                    content.Children.Add(PageUI.Text("«" + phrase + "»"));
                    content.Children.Add(PageUI.Text((exists ? path : "Файл сценария не найден: " + path), true));
                    var buttons = new WrapPanel(); content.Children.Add(buttons);
                    buttons.Children.Add(PageUI.Button(enabled ? "Отключить" : "Включить", async delegate { await Change("registry_toggle", phrase); }));
                    buttons.Children.Add(PageUI.Button("Удалить привязку", async delegate {
                        if (MessageBox.Show(Window.GetWindow(this), "Убрать голосовую фразу «" + phrase + "»? Файл сценария останется.", "Удаление команды", MessageBoxButton.YesNo, MessageBoxImage.Question, MessageBoxResult.No) == MessageBoxResult.Yes)
                            await Change("registry_delete", phrase);
                    }));
                }
                status.Text = count == 0 ? "Голосовых команд пока нет. Создайте первую команду в конструкторе." : "Команд: " + count;
            }
            catch (Exception ex) { status.Text = "Не удалось прочитать команды: " + ex.Message; }
            finally { busy = false; }
        }
        async Task Change(string operation, string phrase)
        {
            await backend.Call("macros", "operation", operation, "phrase", phrase);
            busy = false; await Load();
        }
    }

    sealed class MembersPage : UserControl
    {
        public Task RefreshPage() { return Load(); }
        readonly Backend backend; readonly StackPanel rows = new StackPanel(); readonly TextBlock status = PageUI.Text("", true);
        readonly string[] roles = { "vip", "trusted", "standard", "prankster", "blocked" };
        readonly string[] labels = { "VIP", "Доверенный", "Обычный", "Шутник", "Заблокирован" };
        bool voiceOnly = true, busy;
        public MembersPage(Backend backend)
        {
            this.backend = backend;
            var dock = new DockPanel(); Content = dock;
            var top = new StackPanel(); DockPanel.SetDock(top, Dock.Top); dock.Children.Add(top);
            top.Children.Add(PageUI.Text("VIP защищён; доверенным доступны массовые команды; обычным — личные и случайные; команды шутника обращаются против него; заблокированных помощник не слушает.", true));
            var buttons = new WrapPanel(); top.Children.Add(buttons);
            buttons.Children.Add(PageUI.Button("Сейчас в войсе", async delegate { voiceOnly = true; await Load(); }));
            buttons.Children.Add(PageUI.Button("Все на сервере", async delegate { voiceOnly = false; await Load(); }));
            buttons.Children.Add(PageUI.Button("Обновить", Load)); top.Children.Add(status);
            dock.Children.Add(new ScrollViewer { Content = rows, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled });
            IsVisibleChanged += async delegate { if (IsVisible) await Load(); };
        }
        async Task Load()
        {
            if (busy) return;
            busy = true; rows.IsEnabled = false; status.Text = "Получаю актуальный список…";
            try {
                var data = (Dictionary<string, object>)await backend.Call("members", "operation", "read");
                rows.Children.Clear(); int count = 0;
                foreach (var member in PageUI.Array(data["members"]).Cast<Dictionary<string, object>>()) {
                    if (voiceOnly && !PageUI.Flag(member, "inVoice")) continue;
                    count++;
                    string uid = PageUI.Str(member, "id"), name = PageUI.Str(member, "displayName");
                    if (name == "") name = PageUI.Str(member, "username");
                    var card = new Border { Padding = new Thickness(14), Margin = new Thickness(0, 0, 0, 10), CornerRadius = new CornerRadius(10) };
                    card.SetResourceReference(Border.BackgroundProperty, "ThemeCard"); rows.Children.Add(card);
                    var content = new StackPanel(); card.Child = content;
                    content.Children.Add(PageUI.Text(name + (PageUI.Flag(member, "inVoice") ? " · в войсе" : " · вне войса")));
                    if (PageUI.Flag(member, "protected")) { content.Children.Add(PageUI.Text("VIP · защищён", true)); continue; }
                    var actions = new WrapPanel(); content.Children.Add(actions);
                    var selector = PageUI.Combo(labels); selector.SelectedIndex = Array.IndexOf(roles, PageUI.Str(member, "permission"));
                    actions.Children.Add(selector);
                    selector.SelectionChanged += async delegate {
                        if (selector.SelectedIndex < 0) return;
                        await Change("role", uid, "permission", roles[selector.SelectedIndex]);
                    };
                    if (PageUI.Flag(member, "inVoice")) {
                        bool muted = PageUI.Flag(member, "muted"), deaf = PageUI.Flag(member, "deafened");
                        actions.Children.Add(PageUI.Button(muted ? "Размутить" : "Мут", async delegate { await Change("voice", uid, "voice_action", muted ? "unmute" : "mute"); }));
                        actions.Children.Add(PageUI.Button(deaf ? "Вернуть звук" : "Убрать звук", async delegate { await Change("voice", uid, "voice_action", deaf ? "undeaf" : "deaf"); }));
                        actions.Children.Add(PageUI.Button("Кик", async delegate {
                            if (MessageBox.Show(Window.GetWindow(this), "Отключить от войса: " + name + "?", "Кик", MessageBoxButton.YesNo, MessageBoxImage.Question, MessageBoxResult.No) == MessageBoxResult.Yes)
                                await Change("voice", uid, "voice_action", "disconnect");
                        }));
                    }
                }
                status.Text = "Участников " + (voiceOnly ? "в войсе" : "на сервере") + ": " + count + " · " + DateTime.Now.ToString("HH:mm:ss");
            } catch (Exception ex) { rows.Children.Clear(); status.Text = "Список недоступен: " + ex.Message; }
            finally { busy = false; rows.IsEnabled = true; }
        }
        async Task Change(string operation, string uid, string field, string value)
        {
            if (busy) return;
            busy = true; rows.IsEnabled = false; string error = null;
            try { await backend.Call("members", "operation", operation, "userId", uid, field, value); }
            catch (Exception ex) { error = ex.Message; }
            finally { busy = false; }
            await Load();
            if (error != null) status.Text = "Не выполнено: " + error;
        }
    }

    sealed class MacrosPage : UserControl
    {
        public Task RefreshPage() { return LoadWindows(); }
        sealed class Target { public string Id { get; set; } public string Title { get; set; } }
        readonly Backend backend; readonly string root;
        readonly ComboBox mode = PageUI.Combo(new[] { "Запустить приложение / игру", "Нажатия в окне (офлайн)" });
        readonly ComboBox target = new ComboBox { DisplayMemberPath = "Title", Margin = new Thickness(0, 0, 8, 8) };
        readonly TextBox file = PageUI.Input(), name = PageUI.Input(), phrase = PageUI.Input(), prompt = PageUI.Input(true), preview = PageUI.Input(true);
        readonly TextBlock status = PageUI.Text("Проверка плана ничего не выполняет.", true);
        readonly DispatcherTimer timer = new DispatcherTimer();
        string token = "", savedTitle = ""; bool busy, loading;
        internal static readonly string[][] CommandTemplates = {
            new[] { "Нажать клавишу", "нажми space", "space" },
            new[] { "Сочетание клавиш", "нажми ctrl+a", "ctrl+a" },
            new[] { "Подождать", "жди 1.5", "1.5" },
            new[] { "Удерживать клавишу", "удерживай right 2", "right 2" },
            new[] { "Ввести текст", "текст Hello", "Hello" },
            new[] { "Переместить мышь", "курсор 100 200", "100 200" },
            new[] { "Кликнуть мышью", "клик 100 200", "100 200" }
        };
        public MacrosPage(Backend backend, string root)
        {
            this.backend = backend; this.root = root;
            var body = new StackPanel(); Content = new ScrollViewer { Content = body, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled };
            body.Children.Add(mode); body.Children.Add(PageUI.Text("Открытое окно для нажатий")); body.Children.Add(target);
            var pick = new WrapPanel(); body.Children.Add(pick);
            pick.Children.Add(PageUI.Button("Обновить список окон", LoadWindows));
            pick.Children.Add(PageUI.Button("Выбрать EXE / ярлык", delegate {
                var dialog = new OpenFileDialog { Filter = "Приложения и ярлыки|*.exe;*.lnk;*.url" };
                if (dialog.ShowDialog(Window.GetWindow(this)) == true) file.Text = dialog.FileName;
                return Task.FromResult(0);
            }));
            body.Children.Add(PageUI.Text("Файл приложения (для запуска) / запасной EXE")); body.Children.Add(file);
            body.Children.Add(PageUI.Text("Добавить команду кнопкой"));
            body.Children.Add(PageUI.Text("Кнопки только дописывают строку в конец списка. Выделенные параметры можно сразу заменить. Для простого запуска программы команды не нужны.", true));
            var templates = new WrapPanel(); body.Children.Add(templates);
            foreach (var item in CommandTemplates) {
                var template = item;
                var button = PageUI.Button(template[0], delegate { InsertTemplate(template); return Task.FromResult(0); });
                button.ToolTip = "Добавить: " + template[1]; templates.Children.Add(button);
            }
            body.Children.Add(PageUI.Text("Твои команды — редактируй здесь, по одной на строку")); prompt.Height = 160; body.Children.Add(prompt);
            body.Children.Add(PageUI.Text("Время — в секундах; клавиши — space, enter, right и т. п.; текст — латиницей; координаты мыши — X Y на экране. «Проверить план» проверяет запись, «Выполнить» запускает её после подтверждения.", true));
            var help = new Expander { Header = "Поддерживаемые команды и примеры", Margin = new Thickness(0, 0, 0, 12) };
            help.SetResourceReference(Control.ForegroundProperty, "ThemeText");
            help.Content = PageUI.Text("Запуск: выберите режим запуска и EXE/ярлык, задайте кодовую фразу.\nНажатия: выберите открытое окно локальной игры.\nнажми space · нажми ctrl+a · жди 1.5 · удерживай right 2\nкурсор 100 200 · клик 100 200 · текст Hello\nКлавиши: left/right/up/down, space, enter, esc, tab, f1–f12, a–z, 0–9.\nТекст — латиницей. Импортированный JSON поддерживает повторения.\nМакросы сетевых игр запрещены; простой запуск разрешён.\nСтоп: мышь в левый верхний угол. Потеря фокуса останавливает следующие действия.", true); body.Children.Add(help);
            body.Children.Add(PageUI.Text("Название сценария")); name.Text = "Новый сценарий"; body.Children.Add(name);
            body.Children.Add(PageUI.Text("Кодовая фраза (без имени помощника)")); body.Children.Add(phrase);
            var buttons = new WrapPanel(); body.Children.Add(buttons);
            buttons.Children.Add(PageUI.Button("Проверить план", async delegate { await Plan(); }));
            buttons.Children.Add(PageUI.Button("Открыть сценарий", Open));
            buttons.Children.Add(PageUI.Button("Сохранить .jmacro", Save));
            buttons.Children.Add(PageUI.Button("Выполнить", Run));
            preview.IsReadOnly = true; preview.Height = 220; preview.FontFamily = new FontFamily("Consolas"); body.Children.Add(preview); body.Children.Add(status);
            foreach (var field in new[] { file, name, phrase, prompt }) field.TextChanged += delegate { if (!loading) token = ""; };
            mode.SelectionChanged += delegate { token = ""; };
            target.SelectionChanged += delegate { if (!loading) { savedTitle = ""; token = ""; } };
            timer.Interval = TimeSpan.FromSeconds(1);
            timer.Tick += async delegate {
                if (busy) return;
                try {
                    var data = (Dictionary<string, object>)await backend.Call("macros", "operation", "status");
                    status.Text = PageUI.Str(data, "message"); if (!PageUI.Flag(data, "running")) timer.Stop();
                } catch (Exception ex) { status.Text = ex.Message; timer.Stop(); }
            };
            Unloaded += delegate { timer.Stop(); };
            IsVisibleChanged += async delegate { if (IsVisible) { await LoadWindows(); } else timer.Stop(); };
        }
        internal void SmokeTemplates()
        {
            string previous = prompt.Text;
            int previousMode = mode.SelectedIndex;
            try {
                prompt.Text = "жди 2";
                foreach (var template in CommandTemplates) {
                    string before = prompt.Text;
                    InsertTemplate(template);
                    if (!prompt.Text.StartsWith(before, StringComparison.Ordinal) || prompt.SelectedText != template[2] || mode.SelectedIndex != 1)
                        throw new InvalidOperationException("Command template insertion failed: " + template[0]);
                }
            } finally { prompt.Text = previous; mode.SelectedIndex = previousMode; status.Text = "Проверка плана ничего не выполняет."; }
        }
        void InsertTemplate(string[] template)
        {
            if (prompt.Text.TrimStart().StartsWith("[")) {
                status.Text = "Открыт сценарий в формате JSON. Шаблоны предназначены для обычных строк команд; импортированный текст не изменён.";
                MessageBox.Show(Window.GetWindow(this), status.Text, "Добавление команды");
                return;
            }
            mode.SelectedIndex = 1;
            string prefix = prompt.Text.Length == 0 || prompt.Text.EndsWith("\n") ? "" : Environment.NewLine;
            int start = prompt.Text.Length + prefix.Length;
            prompt.AppendText(prefix + template[1] + Environment.NewLine);
            prompt.Focus();
            prompt.Select(start + template[1].LastIndexOf(template[2], StringComparison.Ordinal), template[2].Length);
            prompt.ScrollToEnd();
            token = ""; preview.Clear();
            status.Text = "Добавлено: " + template[1] + ". Ничего не выполнялось. Выбери окно для нажатий и проверь план.";
        }
        async Task LoadWindows()
        {
            try {
                string oldId = target.SelectedItem is Target ? ((Target)target.SelectedItem).Id : "";
                var data = (Dictionary<string, object>)await backend.Call("macros", "operation", "windows");
                var items = PageUI.Array(data["windows"]).Cast<Dictionary<string, object>>().Select(d => new Target { Id = PageUI.Str(d, "id"), Title = PageUI.Str(d, "title") }).ToArray();
                loading = true; target.ItemsSource = items; target.SelectedItem = items.FirstOrDefault(t => t.Id == oldId); loading = false;
            } catch (Exception ex) { loading = false; status.Text = ex.Message; }
        }
        async Task<bool> Plan()
        {
            IsEnabled = false;
            try {
            token = "";
            var selected = target.SelectedItem as Target;
            var data = (Dictionary<string, object>)await backend.Call("macros", "operation", "plan", "kind", mode.SelectedIndex == 0 ? "launch" : "macro",
                "target", file.Text, "name", name.Text, "phrase", phrase.Text, "prompt", prompt.Text,
                "hwnd", selected == null ? "" : selected.Id, "title", selected == null ? savedTitle : selected.Title);
            token = PageUI.Str(data, "token"); preview.Text = PageUI.Str(data, "preview"); status.Text = "План проверен. Ничего не выполнялось."; return true;
            } finally { IsEnabled = true; }
        }
        async Task Open()
        {
            var dialog = new OpenFileDialog { Filter = "Сценарии|*.jmacro", InitialDirectory = Path.Combine(root, "сценарии") };
            if (dialog.ShowDialog(Window.GetWindow(this)) != true) return;
            var data = (Dictionary<string, object>)await backend.Call("macros", "operation", "load", "path", dialog.FileName);
            var doc = (Dictionary<string, object>)data["document"];
            loading = true;
            mode.SelectedIndex = PageUI.Str(doc, "тип") == "launch" ? 0 : 1;
            file.Text = PageUI.Str(doc, "файл"); name.Text = PageUI.Str(doc, "название"); phrase.Text = PageUI.Str(doc, "кодовая_фраза");
            prompt.Text = new JavaScriptSerializer().Serialize(doc["действия"]);
            target.SelectedIndex = -1; savedTitle = PageUI.Str(doc, "окно"); loading = false; token = "";
            preview.Clear(); status.Text = "Открыт сценарий. Сохранённое окно: " + savedTitle;
        }
        async Task Save()
        {
            await Plan();
            var dialog = new SaveFileDialog { Filter = "Сценарии|*.jmacro", DefaultExt = ".jmacro", FileName = "Сценарий.jmacro", InitialDirectory = Path.Combine(root, "сценарии"), OverwritePrompt = true };
            if (dialog.ShowDialog(Window.GetWindow(this)) != true) return;
            var data = (Dictionary<string, object>)await backend.Call("macros", "operation", "save", "token", token, "path", dialog.FileName);
            status.Text = PageUI.Str(data, "message");
        }
        async Task Run()
        {
            if (busy) return;
            busy = true;
            try {
                await Plan();
                if (MessageBox.Show(Window.GetWindow(this), mode.SelectedIndex == 0 ? "Запустить выбранное приложение?" : "Выполнить проверенные нажатия в выбранном окне?", "Выполнение", MessageBoxButton.YesNo, MessageBoxImage.Question, MessageBoxResult.No) != MessageBoxResult.Yes) return;
                var data = (Dictionary<string, object>)await backend.Call("macros", "operation", "run", "token", token);
                status.Text = PageUI.Str(data, "message"); timer.Start();
            } finally { busy = false; }
        }
    }
}
