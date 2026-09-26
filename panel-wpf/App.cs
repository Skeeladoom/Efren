using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Media;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Markup;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Media.Imaging;
using System.Windows.Threading;

namespace Efren.Panel
{
    // Follow render frames only during scrolling; no forced layout or idle timer.
    sealed class SmoothScrolling
    {
        readonly Stopwatch clock = new Stopwatch();
        ScrollViewer active;
        double position, target, previousTime;
        public SmoothScrolling(Window window)
        {
            window.PreviewMouseWheel += Wheel;
            window.PreviewMouseDown += delegate { Stop(); };
            window.PreviewKeyDown += delegate { Stop(); };
            window.Closed += delegate { Stop(); };
        }
        void Frame(object sender, EventArgs e)
        {
            if (active == null || !active.IsVisible) { Stop(); return; }
            double now = clock.Elapsed.TotalMilliseconds;
            double elapsed = now - previousTime;
            previousTime = now;
            target = Math.Max(0, Math.Min(active.ScrollableHeight, target));
            // Frame-rate independent following: repeated wheel ticks extend the
            // destination instead of restarting an easing curve on every tick.
            position += (target - position) * (1 - Math.Exp(-elapsed / 42.0));
            bool finished = Math.Abs(target - position) < 0.4;
            active.ScrollToVerticalOffset(finished ? target : position);
            if (finished) Stop();
        }
        void Stop() { CompositionTarget.Rendering -= Frame; clock.Reset(); active = null; }
        static DependencyObject Parent(DependencyObject node)
        {
            var content = node as FrameworkContentElement;
            if (content != null) return content.Parent;
            if (node is Visual || node is System.Windows.Media.Media3D.Visual3D) return VisualTreeHelper.GetParent(node);
            return LogicalTreeHelper.GetParent(node);
        }
        void Wheel(object sender, MouseWheelEventArgs e)
        {
            if (e.Handled || Keyboard.Modifiers != ModifierKeys.None || !SystemParameters.ClientAreaAnimation) return;
            var viewers = new List<ScrollViewer>();
            for (var node = e.OriginalSource as DependencyObject; node != null; node = Parent(node))
            {
                // Native controls keep their own editing/selection and scrolling behavior.
                if (node is System.Windows.Controls.Primitives.TextBoxBase || node is PasswordBox || node is System.Windows.Controls.Primitives.Selector) return;
                var viewer = node as ScrollViewer;
                if (viewer != null) viewers.Add(viewer);
            }
            foreach (var viewer in viewers)
            {
                double current = active == viewer ? target : viewer.VerticalOffset;
                // Reverse immediately instead of first consuming pending travel.
                if (active == viewer && (target - position) * e.Delta > 0) current = position;
                if (viewer.ScrollableHeight <= 0 || (e.Delta > 0 ? current <= 0 : current >= viewer.ScrollableHeight)) continue;
                int lines = SystemParameters.WheelScrollLines;
                if (lines == 0) return;
                // Logical scrolling (item units) is left to the control itself.
                if (viewer.CanContentScroll) return;
                double distance = lines < 0 ? viewer.ViewportHeight : lines * 32.0;
                Begin(viewer, current - e.Delta / 120.0 * distance);
                e.Handled = true;
                return;
            }
        }
        internal void Begin(ScrollViewer viewer, double destination)
        {
            if (active != viewer)
            {
                Stop();
                active = viewer;
                position = viewer.VerticalOffset;
                previousTime = 0;
                clock.Restart();
                CompositionTarget.Rendering += Frame;
            }
            target = Math.Max(0, Math.Min(viewer.ScrollableHeight, destination));
        }
    }

    sealed class Backend : IDisposable
    {
        readonly Process process;
        readonly SemaphoreSlim gate = new SemaphoreSlim(1, 1);
        readonly JavaScriptSerializer json = new JavaScriptSerializer();
        public int Pid { get { return process.Id; } }
        public Backend(string root)
        {
            string python = Path.Combine(root, "runtime", "python", "python.exe");
            if (!File.Exists(python) && File.Exists(Path.Combine(root, "lite-build.json")))
                throw new FileNotFoundException("В сборке Lite отсутствует встроенный Python. Восстановите комплект runtime/python.", python);
            if (!File.Exists(python))
                python = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Python", "Python313", "python.exe");
            if (!File.Exists(python)) throw new FileNotFoundException("Не найден Python для существующих обработчиков", python);
            var info = new ProcessStartInfo(python, "-u \"" + Path.Combine(root, "panel_backend.py") + "\"");
            info.WorkingDirectory = root;
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            info.RedirectStandardInput = true;
            info.RedirectStandardOutput = true;
            info.RedirectStandardError = true;
            info.StandardOutputEncoding = Encoding.UTF8;
            info.StandardErrorEncoding = Encoding.UTF8;
            info.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
            info.EnvironmentVariables["PYTHONNOUSERSITE"] = "1";
            info.EnvironmentVariables.Remove("PYTHONHOME");
            info.EnvironmentVariables.Remove("PYTHONPATH");
            process = Process.Start(info);
            process.ErrorDataReceived += delegate { }; // Drain errors without exposing arbitrary backend output in UI.
            process.BeginErrorReadLine();
        }
        public async Task<object> Call(string action, params object[] pairs)
        {
            await gate.WaitAsync();
            try
            {
                if (process.HasExited) throw new InvalidOperationException("Обработчик панели остановлен. Откройте панель заново.");
                var request = new Dictionary<string, object> { { "action", action } };
                for (int i = 0; i < pairs.Length; i += 2) request[(string)pairs[i]] = pairs[i + 1];
                // JSON uses Unicode escapes so the pipe never depends on the Windows code page.
                string payload = json.Serialize(request);
                var ascii = new StringBuilder();
                foreach (char c in payload) ascii.Append(c > 127 ? "\\u" + ((int)c).ToString("x4") : c.ToString());
                await process.StandardInput.WriteLineAsync(ascii.ToString());
                await process.StandardInput.FlushAsync();
                var read = process.StandardOutput.ReadLineAsync();
                if (await Task.WhenAny(read, Task.Delay(45000)) != read)
                {
                    process.Kill();
                    throw new TimeoutException("Обработчик не ответил. Проверьте состояние помощника перед повтором команды.");
                }
                string line = await read;
                if (line == null) throw new IOException("Связь с обработчиком панели закрыта.");
                var response = json.Deserialize<Dictionary<string, object>>(line);
                if (!Convert.ToBoolean(response["ok"])) throw new InvalidOperationException(Convert.ToString(response["error"]));
                return response["data"];
            }
            finally { gate.Release(); }
        }
        public void Dispose()
        {
            try { process.StandardInput.Close(); if (!process.WaitForExit(700)) process.Kill(); } catch { }
            process.Dispose();
        }
    }

    sealed class PanelController
    {
        public sealed class Correction
        {
            public string Wrong { get; set; }
            public string Correct { get; set; }
            public string Label { get { return Wrong + " → " + Correct; } }
        }
        bool trainingBusy;
        bool diagnosticsBusy;
        string[] favoriteCommands = new string[0];
        readonly Window window;
        readonly SmoothScrolling scrolling;
        readonly Backend backend;
        readonly Appearance appearance;
        readonly Dictionary<string, string> replyGroups = new Dictionary<string, string> {
            {"ReplyDefault", "default"}, {"ReplyKick", "disconnect"}, {"ReplySelf", "self_disconnect"},
            {"ReplyRandom", "random_disconnect"}, {"ReplyAll", "genocide"}
        };
        readonly string[] replyModes = { "voice", "sound", "log", "none" };
        bool sendingConsole;
        AppearanceEditor appearanceEditor;
        readonly string root;
        readonly DispatcherTimer timer = new DispatcherTimer();
        readonly Dictionary<string, SoundPlayer> sounds = new Dictionary<string, SoundPlayer>();
        bool soundsEnabled, closeSoundPlayed;
        readonly bool smokeMode = Environment.GetCommandLineArgs().Contains("--smoke");
        readonly Dictionary<string, string> toggleKeys = new Dictionary<string, string> {
            {"VoiceEnabled", "voice_enabled"}, {"TtsEnabled", "tts_enabled"},
            {"DiscordEnabled", "discord_commands_enabled"}, {"WindowsEnabled", "windows_commands_enabled"},
            {"FriendsVoice", "friends_voice_enabled"}, {"FriendsCommands", "friends_can_use_discord"},
            {"BrowserClarify", "browser_clarification_enabled"}, {"UiSounds", "ui_sounds_enabled"}
        };
        string[] browserKeys = new string[0];
        string[] browserLabels = new string[0];
        TextBlock jarvisCommandsTitle;
        bool updating, refreshing, closing;
        bool updateBusy;
        string jarvisTransition = "";
        string fridayName = "Пятница", jarvisName = "Джарвис";
        DateTime lastMeasure = DateTime.UtcNow;
        double lastCpu;
        public PanelController(Window window, string root)
        {
            this.window = window; this.root = root;
            if (File.Exists(Path.Combine(root, "lite-build.json"))) ConfigureLite();
            scrolling = new SmoothScrolling(window);
            window.PreviewMouseDown += delegate(object sender, MouseButtonEventArgs e) {
                if (e.ChangedButton != MouseButton.XButton1 && e.ChangedButton != MouseButton.XButton2) return;
                if (!Find<Grid>("RootLayout").IsEnabled || closing) return;
                e.Handled = true;
                Travel(e.ChangedButton == MouseButton.XButton1 ? -1 : 1);
            };
            window.PreviewKeyDown += delegate(object sender, KeyEventArgs e) {
                if (Keyboard.Modifiers != ModifierKeys.Alt || !Find<Grid>("RootLayout").IsEnabled || closing) return;
                Key key = e.Key == Key.System ? e.SystemKey : e.Key;
                if (key == Key.Left || key == Key.Right) { e.Handled = true; Travel(key == Key.Left ? -1 : 1); }
            };
            backend = new Backend(root);
            appearance = new Appearance(window, Path.Combine(root, "panel_theme.json"));
            Find<Button>("ConsoleCommand").Click += async delegate { await SendConsole("command"); };
            Find<Button>("ConsoleSpeech").Click += async delegate { await SendConsole("speech"); };
            Find<Button>("FavoriteAdd").Click += async delegate { await ChangeFavorite("add", Find<TextBox>("ConsoleInput").Text); };
            Find<Button>("FullShutdown").Click += async delegate {
                string prompt = File.Exists(Path.Combine(root, "lite-build.json")) ? "Остановить Джарвиса Lite и отключить микрофон, озвучку и команды? Для возврата включите их в настройках." : "Остановить обоих помощников и выключить речь, озвучку, команды и Qwen в настройках? Для возврата их нужно включить вручную.";
                if (MessageBox.Show(window, prompt, "Полное отключение", MessageBoxButton.YesNo, MessageBoxImage.Warning, MessageBoxResult.No) != MessageBoxResult.Yes) return;
                Find<Button>("FullShutdown").IsEnabled = false;
                try { await backend.Call("full_shutdown"); HideError(); }
                catch (Exception ex) { ShowError(ex.Message); }
                finally { Find<Button>("FullShutdown").IsEnabled = true; }
                await Refresh();
            };
            Find<TextBox>("ConsoleInput").PreviewKeyDown += async delegate(object sender, KeyEventArgs e) {
                if (e.Key == Key.Enter) {
                    e.Handled = true;
                    if (!e.IsRepeat) await SendConsole((Keyboard.Modifiers & ModifierKeys.Control) != 0 ? "speech" : "command");
                }
            };
            foreach (var pair in replyGroups) {
                var group = pair.Value; var box = Find<ComboBox>(pair.Key);
                box.ItemsSource = group == "default" ? new[] { "Голос", "Только журнал", "Без ответа" } : new[] { "Голос", "Звук AWP", "Только журнал", "Без ответа" };
                box.SelectionChanged += async delegate {
                    if (updating || box.SelectedIndex < 0) return;
                    var choices = group == "default" ? new[] { "voice", "log", "none" } : replyModes;
                    box.IsEnabled = false;
                    try { await backend.Call("reply_mode", "group", group, "mode", choices[box.SelectedIndex]); HideError(); PlaySound("Change"); }
                    catch (Exception ex) { ShowError(ex.Message); }
                    finally { box.IsEnabled = true; }
                    await Refresh();
                };
            }
            Find<Button>("Appearance").Click += delegate {
                OpenAppearance();
            };
            soundsEnabled = true;
            try {
                var settings = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(File.ReadAllText(Path.Combine(root, "jarvis_settings.json")));
                if (settings.ContainsKey("ui_sounds_enabled")) soundsEnabled = Flag(settings, "ui_sounds_enabled");
            } catch { }
            if (!smokeMode)
                foreach (string name in new[] { "Open", "Close", "ClickS", "Change", "Excellent", "Block" })
                    try {
                        var player = new SoundPlayer(Path.Combine(root, "sounds", name + ".wav"));
                        player.Load(); sounds[name] = player;
                    } catch { /* Missing UI effects must not prevent startup. */ }
            // Preview happens before modal ShowDialog: no delayed bubbling click on dialog close.
            window.PreviewMouseLeftButtonDown += delegate(object sender, MouseButtonEventArgs e) {
                DependencyObject target = e.OriginalSource as DependencyObject;
                while (target is Visual) {
                    var button = target as Button;
                    if (button != null) { if (button.IsEnabled) PlaySound("ClickS"); break; }
                    target = VisualTreeHelper.GetParent(target);
                }
            };
            window.PreviewKeyDown += delegate(object sender, KeyEventArgs e) {
                if ((e.Key == Key.Enter || e.Key == Key.Space) && Keyboard.FocusedElement is Button) PlaySound("ClickS");
            };
            foreach (var item in toggleKeys)
            {
                var key = item.Value; var box = Find<CheckBox>(item.Key);
                box.Click += async delegate {
                    if (updating) return;
                    box.IsEnabled = false;
                    try {
                        await backend.Call("setting", "key", key, "value", box.IsChecked == true);
                        if (key == "ui_sounds_enabled") soundsEnabled = box.IsChecked == true;
                        if (!soundsEnabled) foreach (var player in sounds.Values) player.Stop();
                        PlaySound("Change"); HideError();
                    }
                    catch (Exception ex) { ShowError(ex.Message); }
                    finally { box.IsEnabled = true; }
                    await Refresh();
                };
            }
            Find<ComboBox>("Browser").ItemsSource = browserLabels;
            Find<ComboBox>("Browser").SelectionChanged += async delegate {
                if (updating) return;
                int index = Find<ComboBox>("Browser").SelectedIndex;
                if (index < 0) return;
                try { await backend.Call("setting", "key", "default_browser", "value", browserKeys[index]); HideError(); }
                catch (Exception ex) { ShowError(ex.Message); }
                await Refresh();
            };
            Bind("FridayStart", "bot", "operation", "start"); Bind("FridayStop", "bot", "operation", "stop"); Bind("FridayRestart", "bot", "operation", "restart");
            BindJarvis("JarvisStart", "start"); BindJarvis("JarvisStop", "stop"); BindJarvis("JarvisRestart", "restart");
            Bind("VoiceRestart", "voice_restart");
            Find<Button>("FridayLog").Click += delegate { OpenNative("friday", "Журнал и команды · " + fridayName); };
            Find<Button>("JarvisLog").Click += delegate { OpenNative("jarvis", "Журнал · " + jarvisName); };
            Find<Button>("Roles").Click += delegate { OpenNative("members", "Участники войса"); };
            Find<Button>("Training").Click += async delegate {
                Navigate("TrainingPage", "Обучение распознавания", "Словарь исправлений · " + fridayName);
                await UpdateTraining("read");
            };
            Find<Button>("TrainingRefresh").Click += async delegate { await UpdateTraining("read"); };
            Find<Button>("TrainingSave").Click += async delegate { await UpdateTraining("save"); };
            Find<Button>("TrainingDelete").Click += async delegate { await UpdateTraining("delete"); };
            Find<ListBox>("TrainingRecent").SelectionChanged += delegate {
                var value = Find<ListBox>("TrainingRecent").SelectedItem as string;
                if (value != null) { Find<TextBox>("TrainingWrong").Text = value; Find<TextBox>("TrainingCorrect").Clear(); Find<ListBox>("TrainingSaved").SelectedIndex = -1; }
            };
            Find<ListBox>("TrainingSaved").SelectionChanged += delegate {
                var value = Find<ListBox>("TrainingSaved").SelectedItem as Correction;
                if (value != null) { Find<TextBox>("TrainingWrong").Text = value.Wrong; Find<TextBox>("TrainingCorrect").Text = value.Correct; }
            };
            Find<Button>("Macros").Click += delegate { OpenNative("macros", "Конструктор сценариев"); };
            Bind("Chat", "window", "window", "chat");
            Bind("Legacy", "window", "window", "legacy"); Bind("Project", "project");
            Find<Button>("Diagnostics").Click += async delegate {
                Navigate("DiagnosticsPage", "Диагностика", "Состояние помощников и статистика по журналу");
                await UpdateDiagnostics(false);
            };
            Find<Button>("DiagnosticsRefresh").Click += async delegate { await UpdateDiagnostics(false); };
            Find<Button>("DiagnosticsCopy").Click += delegate {
                try {
                    Clipboard.SetText(Find<TextBlock>("DiagnosticsSystem").Text + "\n\n" + Find<TextBlock>("DiagnosticsRecognition").Text);
                    Find<TextBlock>("DiagnosticsStatus").Text = "Отчёт скопирован.";
                } catch (Exception ex) { Find<TextBlock>("DiagnosticsStatus").Text = "Не удалось скопировать: " + ex.Message; }
            };
            Find<Button>("DiagnosticsRepair").Click += async delegate {
                if (MessageBox.Show(window, "Проверить и восстановить компоненты? Если мост или распознавание не готовы, Discord-помощник будет перезапущен. Текущая фраза может прерваться.", "Восстановление", MessageBoxButton.YesNo, MessageBoxImage.Question, MessageBoxResult.No) == MessageBoxResult.Yes)
                    await UpdateDiagnostics(true);
            };
            Bind("StartupOn", "startup", "enabled", true); Bind("StartupOff", "startup", "enabled", false);
            Find<Button>("PanelRestart").Click += delegate { Program.RestartRequested = true; window.Close(); };
            Find<Button>("CheckUpdate").Click += async delegate { await CheckForUpdate(); };
            Bind("QwenOff", "setting", "key", "qwen_mode", "value", "disabled");
            Bind("QwenExplicit", "setting", "key", "qwen_mode", "value", "explicit");
            Bind("QwenAuto", "setting", "key", "qwen_mode", "value", "fallback");
            Find<Button>("Refresh").Click += async delegate {
                await Refresh();
                var host = Find<ContentControl>("WorkspacePage");
                if (host.IsVisible) {
                    if (host.Content is JournalPage) await ((JournalPage)host.Content).RefreshPage();
                    else if (host.Content is MembersPage) await ((MembersPage)host.Content).RefreshPage();
                    else if (host.Content is MacrosPage) await ((MacrosPage)host.Content).RefreshPage();
                }
            };
            Find<Button>("NavOverview").Click += delegate { Navigate("OverviewPage", "Твои помощники", "Голос, команды и управление — в одном месте"); };
            Find<Button>("NavSettings").Click += delegate { Navigate("SettingsPage", "Настройки", "Изменения сохраняются сразу"); };
            Find<Button>("NavTools").Click += delegate { Navigate("ToolsPage", "Инструменты", "Диагностика и дополнительные возможности"); };
            WireName("FridayName", "friday"); WireName("JarvisName", "jarvis");
            Find<Button>("Login").Click += async delegate { await Login(); };
            Find<PasswordBox>("Password").KeyDown += async delegate(object sender, KeyEventArgs e) { if (e.Key == Key.Enter) { e.Handled = true; await Login(); } };
            timer.Interval = TimeSpan.FromSeconds(5);
            timer.Tick += async delegate {
                await Refresh();
                if (!smokeMode && window.WindowState != WindowState.Minimized && Find<Grid>("RootLayout").IsEnabled
                    && Find<StackPanel>("DiagnosticsPage").IsVisible && Find<CheckBox>("DiagnosticsAuto").IsChecked == true)
                    await UpdateDiagnostics(false);
            };
            window.Closing += async delegate(object sender, System.ComponentModel.CancelEventArgs e) {
                if (closeSoundPlayed || smokeMode || !soundsEnabled || !sounds.ContainsKey("Close")) return;
                e.Cancel = true; closeSoundPlayed = true; window.IsEnabled = false;
                PlaySound("Close"); await Task.Delay(850); window.Close();
            };
            window.Closed += delegate {
                closing = true; timer.Stop(); backend.Dispose();
                foreach (var player in sounds.Values) player.Dispose();
            };
            window.ContentRendered += delegate { if (!closing && !closeSoundPlayed) PlaySound("Open"); };
            window.Loaded += async delegate {
                Find<PasswordBox>("Password").Focus();
                await Refresh(); timer.Start();
                if (Environment.GetCommandLineArgs().Contains("--smoke")) await Smoke();
            };
        }
        T Find<T>(string name) where T : FrameworkElement { return (T)window.FindName(name); }
        void ConfigureLite()
        {
            window.Title = "EFREN — Джарвис Lite (тестовая сборка)";
            // Keep named controls alive for shared bindings, but hide whole cards.
            foreach (string name in new[] { "FridayName", "RepliesTitle", "FriendsVoice", "QwenOff" })
            {
                DependencyObject node = window.FindName(name) as DependencyObject;
                while (node != null && !(node is Border)) node = LogicalTreeHelper.GetParent(node);
                if (node is Border) ((Border)node).Visibility = Visibility.Collapsed;
            }
            foreach (string name in new[] { "Legacy", "DiscordEnabled", "DiagnosticsRepair" })
                Find<FrameworkElement>(name).Visibility = Visibility.Collapsed;
            var shutdownCard = (StackPanel)LogicalTreeHelper.GetParent(Find<Button>("FullShutdown"));
            ((TextBlock)shutdownCard.Children[0]).Text = "Полное отключение Джарвиса Lite";
            ((TextBlock)shutdownCard.Children[1]).Text = "Остановит только локального Джарвиса и отключит его речь, озвучку и команды. Основных помощников не затронет.";
            Find<Button>("FullShutdown").Content = "Остановить и отключить Джарвиса";
            var diagnosticPage = Find<StackPanel>("DiagnosticsPage");
            ((TextBlock)diagnosticPage.Children[diagnosticPage.Children.Count - 1]).Text = "Локальная диагностика Lite. Проверка наличия файлов не заменяет проверку контрольных сумм. Микрофон не включается.";
            foreach (string name in new[] { "JarvisStart", "JarvisStop", "JarvisRestart" })
            {
                var button = Find<Button>(name);
                button.ToolTip = "Управление только Джарвисом из этой папки Lite.";
            }
            Find<TextBlock>("PageDescription").Text = "Джарвис Lite · GigaAM на CPU · локальные команды и оформление";
            var help = new StackPanel();
            jarvisCommandsTitle = PageUI.Text("Команды помощника");
            help.Children.Add(jarvisCommandsTitle);
            help.Children.Add(PageUI.Text("Например: «который час», «открой блокнот», «открой калькулятор», «открой настройки», «сверни окно», «сделай скриншот», «громкость 30», «запусти Доту». Голосом добавляйте имя помощника. Игры и приложения должны быть установлены."));
            help.Children.Add(PageUI.Text("Свои игры и ярлыки привязывайте к фразам через конструктор. Пути к программам на компьютере автора не переносятся. Qwen и управление общим Discord-ботом в Lite не включены.", true));
            var helpCard = new Border { Child = help, Style = (Style)window.FindResource("Card") };
            Find<StackPanel>("ToolsPage").Children.Add(helpCard);
        }
        async Task UpdateDiagnostics(bool repair)
        {
            if (diagnosticsBusy || closing) return;
            diagnosticsBusy = true;
            Find<Button>("DiagnosticsRefresh").IsEnabled = Find<Button>("DiagnosticsRepair").IsEnabled = false;
            Find<TextBlock>("DiagnosticsStatus").Text = repair ? "Восстановление…" : "Проверяю…";
            try {
                string message = "";
                if (repair) {
                    var result = (Dictionary<string, object>)await backend.Call("repair");
                    message = Convert.ToString(result["message"]) + " ";
                }
                var data = (Dictionary<string, object>)await backend.Call("diagnostics");
                Find<TextBlock>("DiagnosticsSystem").Text = Convert.ToString(data["system"]);
                Find<TextBlock>("DiagnosticsRecognition").Text = Convert.ToString(data["recognition"]);
                Find<TextBlock>("DiagnosticsStatus").Text = message + "Проверено: " + DateTime.Now.ToString("HH:mm:ss");
            } catch (Exception ex) { Find<TextBlock>("DiagnosticsStatus").Text = "Ошибка: " + ex.Message; }
            finally {
                diagnosticsBusy = false;
                Find<Button>("DiagnosticsRefresh").IsEnabled = Find<Button>("DiagnosticsRepair").IsEnabled = true;
            }
        }
        async Task ChangeFavorite(string operation, string text)
        {
            try { await backend.Call("favorite", "operation", operation, "text", text); HideError(); await Refresh(); }
            catch (Exception ex) { Find<TextBlock>("ConsoleStatus").Text = ex.Message; }
        }
        void UpdateFavorites(Dictionary<string, object> settings)
        {
            var raw = settings.ContainsKey("friday_favorite_commands") ? settings["friday_favorite_commands"] as System.Collections.IEnumerable : null;
            var values = raw == null ? new string[0] : raw.Cast<object>().OfType<string>().Take(8).ToArray();
            if (favoriteCommands.SequenceEqual(values)) return;
            favoriteCommands = values;
            var host = Find<WrapPanel>("Favorites"); host.Children.Clear();
            foreach (string value in values) {
                string command = value;
                var button = new Button { Content = command, MaxWidth = 340, ToolTip = command + "\nПравый клик — удалить из избранного" };
                button.Click += async delegate { if (sendingConsole) return; Find<TextBox>("ConsoleInput").Text = command; await SendConsole("command"); };
                button.PreviewMouseRightButtonUp += async delegate(object sender, MouseButtonEventArgs e) { e.Handled = true; await ChangeFavorite("remove", command); };
                host.Children.Add(button);
            }
        }
        async Task UpdateTraining(string operation)
        {
            if (trainingBusy) return;
            var selected = Find<ListBox>("TrainingSaved").SelectedItem as Correction;
            if (operation == "delete" && selected == null) { Find<TextBlock>("TrainingStatus").Text = "Выберите запись справа."; return; }
            trainingBusy = true;
            foreach (var name in new[] { "TrainingSave", "TrainingDelete", "TrainingRefresh" }) Find<Button>(name).IsEnabled = false;
            try {
                var data = (Dictionary<string, object>)await backend.Call("training", "operation", operation,
                    "wrong", operation == "delete" ? selected.Wrong : Find<TextBox>("TrainingWrong").Text,
                    "correct", Find<TextBox>("TrainingCorrect").Text);
                var items = (Dictionary<string, object>)data["replacements"];
                Find<ListBox>("TrainingSaved").ItemsSource = items.Select(p => new Correction { Wrong = p.Key, Correct = Convert.ToString(p.Value) }).ToArray();
                Find<ListBox>("TrainingRecent").ItemsSource = ((System.Collections.IEnumerable)data["recent"]).Cast<object>().Select(Convert.ToString).ToArray();
                Find<TextBlock>("TrainingStatus").Text = operation == "save" ? "Исправление сохранено и уже действует." : operation == "delete" ? "Исправление удалено." : "Список обновлён. Выберите фразу или введите свою.";
                if (operation != "read") PlaySound("Change");
            } catch (Exception ex) { Find<TextBlock>("TrainingStatus").Text = "Ошибка: " + ex.Message; }
            finally {
                trainingBusy = false;
                foreach (var name in new[] { "TrainingSave", "TrainingDelete", "TrainingRefresh" }) Find<Button>(name).IsEnabled = true;
            }
        }
        async Task SendConsole(string mode)
        {
            if (sendingConsole || closing) return;
            var input = Find<TextBox>("ConsoleInput");
            string text = input.Text.Trim();
            if (text.Length == 0) { Find<TextBlock>("ConsoleStatus").Text = "Сначала введите текст."; return; }
            sendingConsole = true;
            Find<Button>("ConsoleCommand").IsEnabled = Find<Button>("ConsoleSpeech").IsEnabled = false;
            input.IsReadOnly = true;
            Find<TextBlock>("ConsoleStatus").Text = "Передаю запрос…";
            try {
                var response = (Dictionary<string, object>)await backend.Call("console", "mode", mode, "text", text);
                input.Clear();
                Find<TextBlock>("ConsoleStatus").Text = mode == "command" ? "Команда принята. Результат — в журнале." : "Текст принят на озвучивание (это ещё не подтверждение воспроизведения).";
                if (response.ContainsKey("result")) Find<TextBlock>("ConsoleStatus").Text = Convert.ToString(response["result"]);
            } catch (Exception ex) { Find<TextBlock>("ConsoleStatus").Text = "Ошибка: " + ex.Message; }
            finally {
                sendingConsole = false; input.IsReadOnly = false;
                Find<Button>("ConsoleCommand").IsEnabled = Find<Button>("ConsoleSpeech").IsEnabled = true;
                if (!closing) input.Focus();
            }
        }
        void PlaySound(string name)
        {
            SoundPlayer player;
            if (!smokeMode && soundsEnabled && sounds.TryGetValue(name, out player))
                try { player.Play(); } catch { }
        }
        void ShowError(string message) { Find<TextBlock>("ErrorText").Text = message; Find<Border>("ErrorBar").Visibility = Visibility.Visible; }
        void HideError() { Find<Border>("ErrorBar").Visibility = Visibility.Collapsed; }
        void Bind(string name, string action, params object[] pairs)
        {
            var button = Find<Button>(name);
            button.Click += async delegate {
                button.IsEnabled = false;
                try { await backend.Call(action, pairs); HideError(); await Refresh(); }
                catch (Exception ex) { ShowError(ex.Message); }
                finally { if (!closing) button.IsEnabled = true; }
            };
        }
        void BindJarvis(string name, string operation)
        {
            var button = Find<Button>(name);
            button.Click += async delegate {
                button.IsEnabled = false;
                jarvisTransition = operation == "stop" ? "stopping" : "starting";
                Find<TextBlock>("JarvisState").Text = operation == "stop" ? "◌ Останавливается…" : "◌ Запускается…";
                try { await backend.Call("jarvis", "operation", operation); HideError(); }
                catch (Exception ex) { jarvisTransition = ""; ShowError(ex.Message); }
                finally { if (!closing) button.IsEnabled = true; }
                await Refresh();
            };
        }
        async Task Login()
        {
            var button = Find<Button>("Login");
            if (!button.IsEnabled) return;
            button.IsEnabled = false;
            try
            {
                var result = (Dictionary<string, object>)await backend.Call("authenticate", "password", Find<PasswordBox>("Password").Password);
                Find<PasswordBox>("Password").Clear();
                if (!Convert.ToBoolean(result["authenticated"])) { PlaySound("Block"); Find<TextBlock>("LoginError").Text = "Неверный пароль"; return; }
                PlaySound("Excellent");
                Find<Border>("LoginOverlay").Visibility = Visibility.Collapsed;
                Find<Grid>("RootLayout").IsEnabled = true;
                Find<Grid>("RootLayout").BeginAnimation(UIElement.OpacityProperty, new DoubleAnimation(0.5, 1, TimeSpan.FromMilliseconds(180)));
                Keyboard.ClearFocus();
            }
            catch (Exception ex) { Find<TextBlock>("LoginError").Text = ex.Message; }
            finally { button.IsEnabled = true; }
        }
        static Version ParseVersion(string value)
        {
            value = (value ?? "0.0.0").Trim().TrimStart('v', 'V');
            int suffix = value.IndexOfAny(new[] { '-', '+' });
            if (suffix >= 0) value = value.Substring(0, suffix);
            Version result;
            return Version.TryParse(value, out result) ? result : new Version(0, 0, 0);
        }
        static string Sha256(string path)
        {
            using (var stream = File.OpenRead(path))
            using (var algorithm = SHA256.Create())
                return BitConverter.ToString(algorithm.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
        }
        async Task CheckForUpdate()
        {
            if (updateBusy || !File.Exists(Path.Combine(root, "lite-build.json"))) return;
            updateBusy = true;
            var button = Find<Button>("CheckUpdate");
            var status = Find<TextBlock>("UpdateStatus");
            var progress = Find<ProgressBar>("UpdateProgress");
            button.IsEnabled = false;
            progress.Visibility = Visibility.Collapsed;
            try
            {
                status.Text = "Проверяю последний выпуск GitHub…";
                string localText = File.ReadAllText(Path.Combine(root, "lite-build.json"), Encoding.UTF8);
                var local = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(localText);
                string current = local.ContainsKey("version") ? Convert.ToString(local["version"]) : "0.0.0";
                string repository = local.ContainsKey("release_repository") ? Convert.ToString(local["release_repository"]) : "Skeeladoom/Efren";
                Dictionary<string, object> release;
                using (var web = new WebClient())
                {
                    web.Headers[HttpRequestHeader.UserAgent] = "EFREN-Lite-Updater/" + current;
                    web.Headers[HttpRequestHeader.Accept] = "application/vnd.github+json";
                    string json = await web.DownloadStringTaskAsync(new Uri("https://api.github.com/repos/" + repository + "/releases/latest"));
                    release = new JavaScriptSerializer { MaxJsonLength = 4 * 1024 * 1024 }.Deserialize<Dictionary<string, object>>(json);
                }
                string latest = Convert.ToString(release["tag_name"]).TrimStart('v', 'V');
                if (ParseVersion(latest) <= ParseVersion(current))
                {
                    status.Text = "Установлена актуальная версия " + current + ".";
                    return;
                }
                Dictionary<string, object> setup = null;
                foreach (object item in (object[])release["assets"])
                {
                    var asset = (Dictionary<string, object>)item;
                    if (String.Equals(Convert.ToString(asset["name"]), "EFREN-Lite-Setup.exe", StringComparison.OrdinalIgnoreCase)) { setup = asset; break; }
                }
                if (setup == null) throw new InvalidOperationException("В выпуске " + latest + " нет EFREN-Lite-Setup.exe.");
                string digest = setup.ContainsKey("digest") ? Convert.ToString(setup["digest"]) : "";
                if (!digest.StartsWith("sha256:", StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException("GitHub не предоставил SHA-256 установщика. Обновление отменено.");
                if (MessageBox.Show(window, "Доступна EFREN Lite " + latest + ". Скачать и установить обновление?", "Обновление EFREN Lite", MessageBoxButton.YesNo, MessageBoxImage.Question, MessageBoxResult.Yes) != MessageBoxResult.Yes)
                {
                    status.Text = "Обновление " + latest + " отложено.";
                    return;
                }
                string directory = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "EFREN-Lite", "updates");
                Directory.CreateDirectory(directory);
                string target = Path.Combine(directory, "EFREN-Lite-Setup-" + latest + ".exe");
                progress.Value = 0; progress.Visibility = Visibility.Visible;
                using (var web = new WebClient())
                {
                    web.Headers[HttpRequestHeader.UserAgent] = "EFREN-Lite-Updater/" + current;
                    web.DownloadProgressChanged += delegate(object sender, DownloadProgressChangedEventArgs e) {
                        progress.Value = e.ProgressPercentage;
                        status.Text = "Скачиваю " + latest + ": " + e.ProgressPercentage + "%";
                    };
                    await web.DownloadFileTaskAsync(new Uri(Convert.ToString(setup["browser_download_url"])), target);
                }
                string expected = digest.Substring(7).Trim().ToLowerInvariant();
                string actual = await Task.Run(() => Sha256(target));
                if (actual != expected) { File.Delete(target); throw new InvalidDataException("SHA-256 установщика не совпал. Файл удалён."); }
                status.Text = "Проверка пройдена. Запускаю установщик " + latest + "…";
                Process.Start(new ProcessStartInfo(target, "/SILENT /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS") { UseShellExecute = true });
                closing = true;
                window.Close();
            }
            catch (WebException ex) { status.Text = "Не удалось проверить обновления: " + ex.Message; }
            catch (Exception ex) { status.Text = "Обновление отменено: " + ex.Message; }
            finally
            {
                updateBusy = false;
                if (!closing) button.IsEnabled = true;
            }
        }
        void WireName(string control, string key)
        {
            var field = Find<TextBox>(control);
            field.KeyDown += async delegate(object sender, KeyEventArgs e) {
                if (e.Key == Key.Escape) { field.Text = key == "friday" ? fridayName : jarvisName; Keyboard.ClearFocus(); e.Handled = true; }
                if (e.Key == Key.Enter) { e.Handled = true; await SaveName(field, key); Keyboard.ClearFocus(); }
            };
            field.LostKeyboardFocus += async delegate { await SaveName(field, key); };
        }
        async Task SaveName(TextBox field, string key)
        {
            string oldName = key == "friday" ? fridayName : jarvisName;
            if (updating || !field.IsEnabled || field.Text.Trim() == oldName) return;
            field.IsEnabled = false;
            try { var result = (Dictionary<string, object>)await backend.Call("name", "key", key, "value", field.Text.Trim()); SetNames(result); HideError(); }
            catch (Exception ex) { field.Text = oldName; ShowError(ex.Message); }
            finally { field.IsEnabled = true; }
        }
        void SetNames(Dictionary<string, object> values)
        {
            string oldJarvisName = jarvisName;
            fridayName = Convert.ToString(values["friday"]); jarvisName = Convert.ToString(values["jarvis"]);
            ReplaceAssistantName(window, oldJarvisName, jarvisName);
            Find<TextBlock>("ConsoleTitle").Text = "Команды и озвучка · " + (File.Exists(Path.Combine(root, "lite-build.json")) ? jarvisName : fridayName);
            Find<TextBlock>("RepliesTitle").Text = "Ответы · " + fridayName;
            if (!Find<TextBox>("FridayName").IsKeyboardFocused) Find<TextBox>("FridayName").Text = fridayName;
            if (!Find<TextBox>("JarvisName").IsKeyboardFocused) Find<TextBox>("JarvisName").Text = jarvisName;
            Find<TextBlock>("FridayHint").Text = "Обращение: «" + fridayName + ", рулетка»";
            Find<TextBlock>("JarvisHint").Text = "Обращение: «" + jarvisName + ", открой настройки»";
            Find<Button>("FridayLog").ToolTip = "Журнал и команды: " + fridayName;
            Find<Button>("JarvisLog").ToolTip = "Журнал: " + jarvisName;
            if (jarvisCommandsTitle != null) jarvisCommandsTitle.Text = "Команды: " + jarvisName;
        }
        static string ReplaceWholeName(string value, string oldName, string newName)
        {
            if (String.IsNullOrEmpty(value) || String.IsNullOrEmpty(oldName)) return value;
            int position = 0;
            while ((position = value.IndexOf(oldName, position, StringComparison.Ordinal)) >= 0)
            {
                int after = position + oldName.Length;
                bool leftIsWord = position > 0 && Char.IsLetterOrDigit(value[position - 1]);
                bool rightIsWord = after < value.Length && Char.IsLetterOrDigit(value[after]);
                if (!leftIsWord && !rightIsWord)
                {
                    value = value.Substring(0, position) + newName + value.Substring(after);
                    position += newName.Length;
                }
                else position = after;
            }
            return value;
        }
        static void ReplaceAssistantName(DependencyObject parent, string oldName, string newName)
        {
            if (String.IsNullOrWhiteSpace(oldName) || oldName == newName) return;
            var text = parent as TextBlock;
            if (text != null && text.Text != null) text.Text = ReplaceWholeName(text.Text, oldName, newName);
            var content = parent as ContentControl;
            if (content != null && content.Content is string) content.Content = ReplaceWholeName((string)content.Content, oldName, newName);
            var header = parent as HeaderedContentControl;
            if (header != null && header.Header is string) header.Header = ReplaceWholeName((string)header.Header, oldName, newName);
            var titleWindow = parent as Window;
            if (titleWindow != null && titleWindow.Title != null) titleWindow.Title = ReplaceWholeName(titleWindow.Title, oldName, newName);
            foreach (object child in LogicalTreeHelper.GetChildren(parent))
            {
                var dependencyChild = child as DependencyObject;
                if (dependencyChild != null) ReplaceAssistantName(dependencyChild, oldName, newName);
            }
        }
        static bool Flag(Dictionary<string, object> values, string key) { return values.ContainsKey(key) && values[key] is bool && (bool)values[key]; }
        async Task Refresh()
        {
            if (refreshing || closing) return;
            refreshing = true;
            try
            {
                var data = (Dictionary<string, object>)await backend.Call("status");
                if (closing) return;
                if (data.ContainsKey("edition") && Convert.ToString(data["edition"]) == "lite")
                {
                    bool firstRun = Flag(data, "first_run");
                    var loginFields = (StackPanel)((Border)Find<Border>("LoginOverlay").Child).Child;
                    ((TextBlock)loginFields.Children[0]).Text = firstRun ? "Первый запуск Lite" : "С возвращением";
                    ((TextBlock)loginFields.Children[1]).Text = firstRun ? "Придумайте свой пароль: от 6 символов. Запомните его — это локальный пароль панели." : "Введите свой пароль Lite";
                    Find<Button>("Login").Content = firstRun ? "Создать пароль и войти" : "Войти";
                }
                updating = true;
                SetNames((Dictionary<string, object>)data["names"]);
                var settings = (Dictionary<string, object>)data["settings"];
                UpdateFavorites(settings);
                var replies = settings.ContainsKey("friday_reply_modes") ? settings["friday_reply_modes"] as Dictionary<string, object> : null;
                foreach (var pair in replyGroups) {
                    var choices = pair.Value == "default" ? new[] { "voice", "log", "none" } : replyModes;
                    string replyMode = replies != null && replies.ContainsKey(pair.Value) ? Convert.ToString(replies[pair.Value]) : pair.Value == "default" ? "voice" : "sound";
                    Find<ComboBox>(pair.Key).SelectedIndex = Array.IndexOf(choices, replyMode);
                }
                Find<TextBlock>("StartupState").Text = Flag(data, "startup_enabled") ? "Новая панель запускается вместе с Windows." : Flag(data, "legacy_startup") ? "В автозапуске прежняя панель. «Включить» заменит её новой." : "Автозапуск панели выключен.";
                soundsEnabled = Flag(settings, "ui_sounds_enabled");
                var browsers = (Dictionary<string, object>)data["browsers"];
                if (!browserKeys.SequenceEqual(browsers.Keys)) {
                    browserKeys = browsers.Keys.ToArray();
                    browserLabels = browsers.Values.Select(Convert.ToString).ToArray();
                    Find<ComboBox>("Browser").ItemsSource = browserLabels;
                }
                foreach (var item in toggleKeys) Find<CheckBox>(item.Key).IsChecked = Flag(settings, item.Value);
                string browser = settings.ContainsKey("default_browser") ? Convert.ToString(settings["default_browser"]) : "chrome";
                Find<ComboBox>("Browser").SelectedIndex = Array.IndexOf(browserKeys, browser);
                string mode = Convert.ToString(settings["qwen_mode"]);
                Find<TextBlock>("QwenState").Text = mode == "disabled" ? "Сейчас: отключена" : mode == "explicit" ? "Сейчас: только по команде «спроси Квена»" : "Сейчас: для неизвестных запросов";
                var friday = (Dictionary<string, object>)data["friday"];
                string status = !Flag(data, "bridge") ? "● Не подключена" : !Flag(friday, "workerReady") ? "● Запускает распознавание" : !Flag(friday, "ttsReady") ? "● Загружает голос" : "● Готова";
                Find<TextBlock>("FridayState").Text = status;
                string processState = data.ContainsKey("jarvis_state") ? Convert.ToString(data["jarvis_state"]) : (Flag(data, "jarvis_running") ? "running" : "stopped");
                if (processState == "running" || processState == "stopped") jarvisTransition = "";
                string visibleState = jarvisTransition == "stopping" ? "stopping" : processState;
                Find<TextBlock>("JarvisState").Text = visibleState == "running" ? "● Запущен" : visibleState == "starting" ? "◌ Запускается…" : visibleState == "stopping" ? "◌ Останавливается…" : "○ Выключен";
                Find<TextBlock>("Connection").Text = "Обновлено " + DateTime.Now.ToString("HH:mm:ss");
                Measure();
            }
            catch (Exception ex) { if (!closing) { ShowError(ex.Message); Find<TextBlock>("Connection").Text = "Нет связи с обработчиком"; } }
            finally { updating = false; refreshing = false; }
        }
        void Measure()
        {
            try
            {
                using (var own = Process.GetCurrentProcess())
                using (var helper = Process.GetProcessById(backend.Pid))
                {
                    double cpu = own.TotalProcessorTime.TotalMilliseconds + helper.TotalProcessorTime.TotalMilliseconds;
                    double elapsed = (DateTime.UtcNow - lastMeasure).TotalMilliseconds;
                    double percent = lastCpu == 0 ? 0 : Math.Max(0, (cpu - lastCpu) / elapsed / Environment.ProcessorCount * 100);
                    double memory = (own.WorkingSet64 + helper.WorkingSet64) / 1048576.0;
                    Find<TextBlock>("Resources").Text = String.Format("Панель + обработчик: {0:0} МБ  ·  CPU {1:0.0}%", memory, percent);
                    lastCpu = cpu; lastMeasure = DateTime.UtcNow;
                }
            }
            catch { }
        }
        readonly Dictionary<string, UserControl> nativePages = new Dictionary<string, UserControl>();
        sealed class PageVisit
        {
            public string Page, Title, Description, Native;
            public double Scroll;
        }
        readonly List<PageVisit> visits = new List<PageVisit> {
            new PageVisit { Page = "OverviewPage", Title = "Твои помощники", Description = "Голос, команды и управление — в одном месте" }
        };
        int visitIndex;
        void Travel(int direction)
        {
            int next = visitIndex + direction;
            if (next < 0 || next >= visits.Count) return;
            visits[visitIndex].Scroll = Find<ScrollViewer>("MainPages").VerticalOffset;
            visitIndex = next;
            ShowVisit(visits[visitIndex], direction);
        }
        void OpenNative(string key, string title)
        {
            if (!nativePages.ContainsKey(key)) {
                if (key == "members") nativePages[key] = new MembersPage(backend);
                else if (key == "macros") nativePages[key] = new MacrosPage(backend, root);
                else nativePages[key] = new JournalPage(backend, key, delegate {
                    Navigate("SettingsPage", "Настройки", "Изменения сохраняются сразу");
                    Find<TextBlock>("RepliesTitle").BringIntoView();
                });
            }
            Navigate("WorkspacePage", title, "Боковые кнопки мыши: назад / вперёд · Alt+← / Alt+→", key);
        }
        void Navigate(string page, string title, string description, string native = null)
        {
            var current = visits[visitIndex];
            if (current.Page == page && current.Native == native) return;
            current.Scroll = Find<ScrollViewer>("MainPages").VerticalOffset;
            if (visitIndex + 1 < visits.Count) visits.RemoveRange(visitIndex + 1, visits.Count - visitIndex - 1);
            var visit = new PageVisit { Page = page, Title = title, Description = description, Native = native };
            visits.Add(visit);
            if (visits.Count > 100) visits.RemoveAt(0);
            visitIndex = visits.Count - 1;
            ShowVisit(visit, 1);
        }
        void ShowVisit(PageVisit visit, int direction)
        {
            string page = visit.Page;
            if (visit.Native != null) Find<ContentControl>("WorkspacePage").Content = nativePages[visit.Native];
            Find<ScrollViewer>("MainPages").Visibility = page == "AppearancePage" || page == "WorkspacePage" ? Visibility.Collapsed : Visibility.Visible;
            Find<ContentControl>("WorkspacePage").Visibility = page == "WorkspacePage" ? Visibility.Visible : Visibility.Collapsed;
            Find<ContentControl>("AppearancePage").Visibility = page == "AppearancePage" ? Visibility.Visible : Visibility.Collapsed;
            foreach (var key in new[] { "OverviewPage", "SettingsPage", "ToolsPage", "TrainingPage", "DiagnosticsPage" }) Find<StackPanel>(key).Visibility = key == page ? Visibility.Visible : Visibility.Collapsed;
            Find<TextBlock>("PageTitle").Text = visit.Title; Find<TextBlock>("PageDescription").Text = visit.Description;
            window.Dispatcher.BeginInvoke(new Action(delegate {
                if (Object.ReferenceEquals(visits[visitIndex], visit)) Find<ScrollViewer>("MainPages").ScrollToVerticalOffset(visit.Scroll);
            }), DispatcherPriority.Loaded);
            var target = Find<FrameworkElement>(page);
            target.BeginAnimation(UIElement.OpacityProperty, null);
            var shift = new TranslateTransform(); target.RenderTransform = shift;
            if (SystemParameters.ClientAreaAnimation) {
                var duration = TimeSpan.FromMilliseconds(220);
                var easing = new CubicEase { EasingMode = EasingMode.EaseOut };
                target.BeginAnimation(UIElement.OpacityProperty, new DoubleAnimation(0, 1, duration) { EasingFunction = easing, FillBehavior = FillBehavior.Stop });
                shift.BeginAnimation(TranslateTransform.XProperty, new DoubleAnimation(direction * 28, 0, duration) { EasingFunction = easing, FillBehavior = FillBehavior.Stop });
            }
        }
        void OpenAppearance()
        {
            if (appearanceEditor == null) {
                appearanceEditor = appearance.CreateEditor();
                Find<ContentControl>("AppearancePage").Content = appearanceEditor;
            }
            Navigate("AppearancePage", "Оформление", "Цвета и эффекты — отдельно для каждой детали. Нажмите «Сохранить», чтобы запомнить изменения.");
        }
        async Task Smoke()
        {
            if (File.Exists(Path.Combine(root, "lite-build.json")))
            {
                if (!String.IsNullOrEmpty(Find<TextBlock>("ErrorText").Text))
                    throw new InvalidOperationException("Lite backend status failed: " + Find<TextBlock>("ErrorText").Text);
                if (Find<FrameworkElement>("FridayName").IsVisible || Find<FrameworkElement>("QwenOff").IsVisible)
                    throw new InvalidOperationException("Full-edition cards visible in Lite");
                // Validate UI availability without logging in or opening the microphone.
                Find<Border>("LoginOverlay").Visibility = Visibility.Collapsed;
                Find<Grid>("RootLayout").IsEnabled = true;
                window.UpdateLayout();
                if (!Find<Button>("JarvisStart").IsEnabled || !Find<Button>("JarvisStop").IsEnabled)
                    throw new InvalidOperationException("Lite process controls disabled");
                if (!Find<Button>("JarvisLog").IsVisible || !Find<Button>("Chat").IsVisible || !Find<TextBox>("ConsoleInput").IsVisible)
                    throw new InvalidOperationException("Lite journal/chat/console hidden");
                foreach (string soundName in new[] { "Open", "Close", "ClickS", "Change", "Excellent", "Block" })
                    using (var sound = new SoundPlayer(Path.Combine(root, "sounds", soundName + ".wav"))) sound.Load();
                Navigate("SettingsPage", "Настройки", "Lite test");
                await Task.Delay(250);
                if (Find<FrameworkElement>("QwenOff").IsVisible || Find<FrameworkElement>("DiscordEnabled").IsVisible)
                    throw new InvalidOperationException("Discord/Qwen settings visible in Lite");
                Directory.CreateDirectory(Path.Combine(root, "runtime"));
                File.WriteAllText(Path.Combine(root, "runtime", "wpf-lite-smoke.txt"), "OK: Lite backend, hidden Discord/Qwen, enabled local process controls; no authentication or actions performed.");
                window.Close();
                return;
            }
            // Read-only visual test. Backend still rejects mutations without authentication.
            if (Find<Border>("ErrorBar").Visibility == Visibility.Visible)
                throw new InvalidOperationException("Smoke status failed: " + Find<TextBlock>("ErrorText").Text);
            Find<Border>("LoginOverlay").Visibility = Visibility.Collapsed;
            Find<Grid>("RootLayout").IsEnabled = true;
            var beforeTheme = new JavaScriptSerializer().Serialize(appearance.Values);
            OpenAppearance();
            var editor = appearanceEditor;
            appearance.Values["Panel"].First = "#202830";
            appearance.Values["Panel"].Second = "#304840";
            appearance.Values["Panel"].Breathe = true;
            appearance.Apply("Panel");
            await Task.Delay(300); editor.UpdateLayout();
            foreach (var part in Appearance.Parts)
                if (!Object.ReferenceEquals(editor.FindResource("Theme" + part[0]), window.FindResource("Theme" + part[0])))
                    throw new InvalidOperationException("Appearance page shadows live theme: " + part[0]);
            if (!Object.ReferenceEquals(editor.Foreground, window.FindResource("ThemeText")) || !Object.ReferenceEquals(editor.Background, window.FindResource("ThemePanel")))
                throw new InvalidOperationException("Appearance page text/background theme binding failed");
            var editorImage = new RenderTargetBitmap((int)editor.ActualWidth, (int)editor.ActualHeight, 96, 96, PixelFormats.Pbgra32);
            editorImage.Render(editor);
            var editorEncoder = new PngBitmapEncoder(); editorEncoder.Frames.Add(BitmapFrame.Create(editorImage));
            Directory.CreateDirectory(Path.Combine(root, "runtime"));
            using (var stream = File.Create(Path.Combine(root, "runtime", "wpf-appearance-preview.png"))) editorEncoder.Save(stream);
            var otherParts = appearance.Values.Where(p => p.Key != "Panel").ToDictionary(p => p.Key, p => new JavaScriptSerializer().Serialize(p.Value));
            editor.ResetSelected();
            if (new JavaScriptSerializer().Serialize(appearance.Values["Panel"]) != new JavaScriptSerializer().Serialize(Appearance.Defaults()["Panel"]))
                throw new InvalidOperationException("Selected appearance reset failed");
            foreach (var part in otherParts)
                if (new JavaScriptSerializer().Serialize(appearance.Values[part.Key]) != part.Value) throw new InvalidOperationException("Reset changed another appearance part");
            editor.Cancel();
            if (new JavaScriptSerializer().Serialize(appearance.Values) != beforeTheme) throw new InvalidOperationException("Appearance cancel failed");
            string testThemePath = Path.Combine(Path.GetTempPath(), "efren-theme-" + Guid.NewGuid().ToString("N") + ".json");
            var testOwner = new Window();
            try {
                var testTheme = new Appearance(testOwner, testThemePath);
                testTheme.Values["Button"].First = "#123456";
                testTheme.Values["Button"].Breathe = true;
                if (Appearance.ModeOf(testTheme.Values["Button"]) != "breathe") throw new InvalidOperationException("Legacy breathe migration failed");
                foreach (string effect in new[] { "rainbow", "reverse", "wave", "static", "breathe" }) {
                    testTheme.Values["Button"].Mode = effect;
                    testTheme.Apply("Button");
                    testTheme.Save();
                    var stored = new JavaScriptSerializer().Deserialize<Dictionary<string, ColorSetting>>(File.ReadAllText(testThemePath));
                    if (Appearance.ModeOf(stored["Button"]) != effect) throw new InvalidOperationException("Effect persistence failed");
                }
                testTheme.Save();
                var loadedTheme = new Appearance(testOwner, testThemePath);
                if (loadedTheme.Values["Button"].First != "#123456" || !loadedTheme.Values["Button"].Breathe) throw new InvalidOperationException("Appearance persistence failed");
                loadedTheme.Save(); // Existing-file atomic replacement.
            } finally { testOwner.Close(); if (File.Exists(testThemePath)) File.Delete(testThemePath); }
            Navigate("SettingsPage", "Настройки", "Изменения сохраняются сразу");
            await Task.Delay(200); window.UpdateLayout();
            foreach (var item in toggleKeys)
                if (Find<CheckBox>(item.Key).ActualHeight <= 0) throw new InvalidOperationException("Toggle layout failed");
            Find<ComboBox>("Browser").BringIntoView();
            await Task.Delay(200); window.UpdateLayout();
            var settingsImage = new RenderTargetBitmap((int)window.ActualWidth, (int)window.ActualHeight, 96, 96, PixelFormats.Pbgra32);
            settingsImage.Render(window);
            var settingsEncoder = new PngBitmapEncoder(); settingsEncoder.Frames.Add(BitmapFrame.Create(settingsImage));
            Directory.CreateDirectory(Path.Combine(root, "runtime"));
            using (var stream = File.Create(Path.Combine(root, "runtime", "wpf-settings-preview.png"))) settingsEncoder.Save(stream);
            Find<ComboBox>("Browser").IsDropDownOpen = true;
            await Task.Delay(200); window.UpdateLayout();
            Find<ComboBox>("Browser").IsDropDownOpen = false;
            Navigate("ToolsPage", "Инструменты", "Диагностика и дополнительные возможности");
            await Task.Delay(200); window.UpdateLayout();
            Navigate("TrainingPage", "Обучение распознавания", "Проверка страницы");
            Find<ListBox>("TrainingSaved").ItemsSource = new[] { new Correction { Wrong = "тест ошибка", Correct = "тест исправление" } };
            Find<ListBox>("TrainingSaved").SelectedIndex = 0;
            await Task.Delay(200); window.UpdateLayout();
            if (Find<TextBox>("TrainingWrong").Text != "тест ошибка" || Find<TextBox>("TrainingCorrect").Text != "тест исправление") throw new InvalidOperationException("Training selection failed");
            Navigate("OverviewPage", "Твои помощники", "Голос, команды и управление — в одном месте");
            await Task.Delay(400); window.UpdateLayout();
            var image = new RenderTargetBitmap((int)window.ActualWidth, (int)window.ActualHeight, 96, 96, PixelFormats.Pbgra32);
            image.Render(window);
            var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(image));
            Directory.CreateDirectory(Path.Combine(root, "runtime"));
            using (var stream = File.Create(Path.Combine(root, "runtime", "wpf-panel-preview.png"))) encoder.Save(stream);
            foreach (string page in new[] { "friday", "jarvis", "members", "macros" }) {
                OpenNative(page, "Проверка · " + page);
                await Task.Delay(350); window.UpdateLayout();
                var view = nativePages[page];
                if (view is MacrosPage) ((MacrosPage)view).SmokeTemplates();
                if (view.ActualHeight < 100 || view.ActualWidth < 100) throw new InvalidOperationException("Native page layout failed: " + page);
                var shot = new RenderTargetBitmap((int)window.ActualWidth, (int)window.ActualHeight, 96, 96, PixelFormats.Pbgra32);
                shot.Render(window);
                var png = new PngBitmapEncoder(); png.Frames.Add(BitmapFrame.Create(shot));
                using (var stream = File.Create(Path.Combine(root, "runtime", "wpf-" + page + "-preview.png"))) png.Save(stream);
            }
            Navigate("DiagnosticsPage", "Диагностика", "Проверка интерфейса без восстановления компонентов");
            await Task.Delay(100); window.UpdateLayout();
            if (Find<CheckBox>("DiagnosticsAuto").IsChecked != true || Find<Button>("DiagnosticsCopy").ActualWidth <= 0)
                throw new InvalidOperationException("Diagnostics controls missing");
            Navigate("OverviewPage", "Обзор", "Тест навигации");
            int origin = visitIndex;
            Navigate("SettingsPage", "Настройки", "Тест навигации");
            OpenNative("friday", "Журнал");
            OpenNative("macros", "Конструктор");
            var savedMacroPage = nativePages["macros"];
            int end = visitIndex;
            Travel(-1);
            if (visits[visitIndex].Native != "friday" || !Object.ReferenceEquals(Find<ContentControl>("WorkspacePage").Content, nativePages["friday"]))
                throw new InvalidOperationException("Native back navigation failed");
            Travel(1);
            if (visitIndex != end || !Object.ReferenceEquals(Find<ContentControl>("WorkspacePage").Content, savedMacroPage))
                throw new InvalidOperationException("Native forward navigation recreated page");
            Travel(1);
            if (visitIndex != end) throw new InvalidOperationException("History upper bound failed");
            Travel(-1); Travel(-1); Travel(-1);
            if (visitIndex != origin || visits[visitIndex].Page != "OverviewPage") throw new InvalidOperationException("Overview return failed");
            Navigate("ToolsPage", "Инструменты", "Новая ветка истории");
            int branch = visitIndex;
            Travel(1);
            if (visitIndex != branch || visits.Count != branch + 1) throw new InvalidOperationException("Forward history was not cleared");
            Navigate("ToolsPage", "Инструменты", "Повтор");
            if (visitIndex != branch) throw new InvalidOperationException("Duplicate history entry");
            Navigate("SettingsPage", "Настройки", "Проверка прокрутки");
            await Task.Delay(250);
            var scroll = Find<ScrollViewer>("MainPages");
            scroll.ScrollToTop(); window.UpdateLayout();
            double destination = Math.Min(180, scroll.ScrollableHeight);
            if (destination <= 0) throw new InvalidOperationException("Scroll test requires overflowing settings");
            scrolling.Begin(scroll, destination);
            await Task.Delay(70);
            if (scroll.VerticalOffset <= 0 || scroll.VerticalOffset >= destination) throw new InvalidOperationException("Scroll animation has no intermediate position");
            await Task.Delay(240);
            if (Math.Abs(scroll.VerticalOffset - destination) > 1) throw new InvalidOperationException("Scroll animation did not reach target");
            scrolling.Begin(scroll, -100);
            await Task.Delay(240);
            if (scroll.VerticalOffset > 1) throw new InvalidOperationException("Scroll upper clamp failed");
            scrolling.Begin(scroll, scroll.ScrollableHeight + 100);
            // A full-page-distance jump has a longer settling tail than one notch.
            await Task.Delay(500);
            if (Math.Abs(scroll.VerticalOffset - scroll.ScrollableHeight) > 1) throw new InvalidOperationException("Scroll lower clamp failed");
            File.WriteAllText(Path.Combine(root, "runtime", "wpf-smoke.txt"), "OK: layouts; template insertion; back/forward history; native page reuse; branching; smooth scroll intermediate/final positions and bounds; no mutations executed.");
            window.Close();
        }
    }

    static class Program
    {
        internal static bool RestartRequested;
        [STAThread]
        static int Main()
        {
            try
            {
                string root = AppDomain.CurrentDomain.BaseDirectory;
                while (!File.Exists(Path.Combine(root, "panel_backend.py")))
                {
                    var parent = Directory.GetParent(root.TrimEnd(Path.DirectorySeparatorChar));
                    if (parent == null) throw new DirectoryNotFoundException("Панель должна находиться внутри папки проекта EFREN.");
                    root = parent.FullName;
                }
                bool acquired;
                string mutexName = "Local\\EFREN.WpfPanel";
                if (File.Exists(Path.Combine(root, "lite-build.json")))
                {
                    using (var hash = System.Security.Cryptography.SHA256.Create())
                        mutexName = "Local\\EFREN.Lite.Panel." + BitConverter.ToString(hash.ComputeHash(Encoding.UTF8.GetBytes(Path.GetFullPath(root).ToLowerInvariant()))).Replace("-", "").Substring(0, 20);
                }
                using (var mutex = new Mutex(true, mutexName, out acquired))
                {
                    if (!acquired) { MessageBox.Show("Панель управления уже открыта.", "EFREN"); return 0; }
                    var app = new Application();
                    Window window;
                    using (var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("MainWindow.xaml")) window = (Window)XamlReader.Load(stream);
                    string icon = Path.Combine(root, "friday_icon.ico");
                    if (File.Exists(icon)) window.Icon = BitmapFrame.Create(new Uri(icon));
                    var controller = new PanelController(window, root);
                    app.Run(window);
                    GC.KeepAlive(controller);
                }
                if (RestartRequested) Process.Start(new ProcessStartInfo(Assembly.GetExecutingAssembly().Location) { WorkingDirectory = root, UseShellExecute = true });
                return 0;
            }
            catch (Exception ex)
            {
                string log = Path.Combine(Path.GetTempPath(), "efren-wpf-error.txt");
                File.WriteAllText(log, ex.ToString());
                if (!Environment.GetCommandLineArgs().Contains("--smoke")) MessageBox.Show(ex.Message + "\nПодробности: " + log, "Ошибка панели");
                return 1;
            }
        }
    }
}
