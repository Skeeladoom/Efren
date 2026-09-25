using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Web.Script.Serialization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Data;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Animation;

namespace Efren.Panel
{
    public sealed class ColorSetting
    {
        public string First { get; set; }
        public string Second { get; set; }
        public bool Breathe { get; set; }
        public string Mode { get; set; }
        public double Seconds { get; set; }
    }

    sealed class Appearance
    {
        sealed class ColorSource : DependencyObject
        {
            public static readonly DependencyProperty ValueProperty = DependencyProperty.Register("Value", typeof(Color), typeof(ColorSource), new PropertyMetadata(Colors.Black));
            public Color Value { get { return (Color)GetValue(ValueProperty); } set { SetValue(ValueProperty, value); } }
        }
        public static readonly string[][] Parts = {
            new[]{"TitleBar", "Верхняя полоса окна", "#141A16"},
            new[]{"TitleText", "Текст заголовка окна", "#EDF3EE"},
            new[]{"Panel", "Фон панели", "#101411"}, new[]{"Sidebar", "Боковое меню", "#141A16"},
            new[]{"Card", "Карточки разделов", "#191F1B"}, new[]{"Border", "Рамки и разделители", "#2B352E"},
            new[]{"Button", "Кнопки / поле браузера", "#26312A"}, new[]{"ButtonBorder", "Рамки кнопок", "#35453A"},
            new[]{"Hover", "Наведение на кнопки", "#36483C"}, new[]{"Primary", "Кнопки запуска / выбор", "#386347"},
            new[]{"PrimaryBorder", "Рамки кнопок запуска", "#568B67"}, new[]{"Accent", "Акцент и подсветка", "#83D9A3"},
            new[]{"ToggleOn", "Тумблер: включён", "#468D5E"}, new[]{"ToggleOff", "Тумблер: выключен", "#3D4841"},
            new[]{"ToggleThumb", "Кружок тумблера", "#F1F5F2"}, new[]{"Text", "Основной текст", "#EDF3EE"},
            new[]{"Muted", "Подписи и подсказки", "#98A99D"}, new[]{"Scroll", "Ползунок / рамка списка", "#46574B"},
            new[]{"Popup", "Выпадающие списки", "#1C251F"}
        };
        readonly Window owner;
        readonly List<Window> captionWindows = new List<Window>();
        [DllImport("dwmapi.dll")]
        static extern int DwmSetWindowAttribute(IntPtr hwnd, int attribute, ref int value, int size);
        // Native Windows 11 caption; retain resizing, dragging and system buttons.
        void UpdateCaption(Window window)
        {
            var hwnd = new WindowInteropHelper(window).Handle;
            if (hwnd == IntPtr.Zero) return;
            var background = brushes["TitleBar"].Color;
            var foreground = brushes["TitleText"].Color;
            int dark = (background.R * 299 + background.G * 587 + background.B * 114) < 128000 ? 1 : 0;
            int bg = background.R | (background.G << 8) | (background.B << 16);
            int fg = foreground.R | (foreground.G << 8) | (foreground.B << 16);
            DwmSetWindowAttribute(hwnd, 20, ref dark, 4);
            DwmSetWindowAttribute(hwnd, 35, ref bg, 4);
            DwmSetWindowAttribute(hwnd, 36, ref fg, 4);
        }
        public void AttachCaption(Window window)
        {
            captionWindows.Add(window);
            window.SourceInitialized += delegate { UpdateCaption(window); };
            window.Activated += delegate { UpdateCaption(window); };
            window.Deactivated += delegate { UpdateCaption(window); };
            window.Closed += delegate { captionWindows.Remove(window); };
            UpdateCaption(window);
        }
        readonly string path;
        readonly Dictionary<string, SolidColorBrush> brushes = new Dictionary<string, SolidColorBrush>();
        readonly Dictionary<string, ColorSource> sources = new Dictionary<string, ColorSource>();
        public Dictionary<string, ColorSetting> Values;
        public Appearance(Window owner, string path)
        {
            this.owner = owner; this.path = path;
            Values = Defaults();
            try {
                var loaded = new JavaScriptSerializer().Deserialize<Dictionary<string, ColorSetting>>(File.ReadAllText(path));
                foreach (var key in Values.Keys.ToArray()) {
                    ColorSetting item;
                    if (loaded != null && loaded.TryGetValue(key, out item) && Valid(item)) Values[key] = item;
                }
            } catch (IOException) { } catch (ArgumentException) { } catch (InvalidOperationException) { }
            foreach (var part in Parts) {
                var brush = new SolidColorBrush(); brushes[part[0]] = brush;
                var source = new ColorSource(); sources[part[0]] = source;
                BindingOperations.SetBinding(brush, SolidColorBrush.ColorProperty, new Binding("Value") { Source = source });
                owner.Resources["Theme" + part[0]] = brush;
            }
            brushes["TitleBar"].Changed += delegate { foreach (var w in captionWindows) UpdateCaption(w); };
            brushes["TitleText"].Changed += delegate { foreach (var w in captionWindows) UpdateCaption(w); };
            Apply();
            AttachCaption(owner);
            owner.StateChanged += delegate { Apply(); };
            owner.Closed += delegate { foreach (var b in brushes.Values) b.BeginAnimation(SolidColorBrush.ColorProperty, null); };
        }
        static bool Valid(ColorSetting item)
        {
            Color c;
            return item != null && TryColor(item.First, out c) && TryColor(item.Second, out c)
                && !double.IsNaN(item.Seconds) && item.Seconds >= 2 && item.Seconds <= 12;
        }
        public static bool TryColor(string text, out Color color)
        {
            color = Colors.Black;
            if (text == null || text.Length != 7 || text[0] != '#') return false;
            try { color = (Color)ColorConverter.ConvertFromString(text); return true; } catch { return false; }
        }
        public static Dictionary<string, ColorSetting> Defaults()
        {
            return Parts.ToDictionary(p => p[0], p => new ColorSetting { First = p[2], Second = p[2], Seconds = 4 });
        }
        public Dictionary<string, ColorSetting> Copy()
        {
            return new JavaScriptSerializer().Deserialize<Dictionary<string, ColorSetting>>(new JavaScriptSerializer().Serialize(Values));
        }
        public void Apply()
        {
            foreach (var part in Parts) Apply(part[0]);
        }
        public void Apply(string key)
        {
            var value = Values[key]; var brush = brushes[key];
            brush.BeginAnimation(SolidColorBrush.ColorProperty, null);
            sources[key].Value = (Color)ColorConverter.ConvertFromString(value.First);
            string mode = ModeOf(value);
            if (owner.WindowState == WindowState.Minimized) return;
            if (mode == "breathe" && value.First != value.Second) {
                var animation = new ColorAnimation(brush.Color, (Color)ColorConverter.ConvertFromString(value.Second), TimeSpan.FromSeconds(value.Seconds / 2)) {
                    AutoReverse = true, RepeatBehavior = RepeatBehavior.Forever,
                    EasingFunction = new SineEase { EasingMode = EasingMode.EaseInOut }
                };
                Timeline.SetDesiredFrameRate(animation, 20);
                brush.BeginAnimation(SolidColorBrush.ColorProperty, animation);
            }
            else if (mode == "rainbow" || mode == "reverse" || mode == "wave") {
                var animation = new ColorAnimationUsingKeyFrames { Duration = TimeSpan.FromSeconds(value.Seconds), RepeatBehavior = RepeatBehavior.Forever };
                for (int i = 0; i <= 36; i++) {
                    double t = i / 36.0;
                    double hue = mode == "reverse" ? 1 - t : t;
                    double saturation = mode == "wave" ? 0.5 + 0.5 * Math.Cos(2 * Math.PI * t) : 1;
                    double brightness = mode == "wave" ? 0.55 + 0.45 * Math.Cos(4 * Math.PI * t) : 1;
                    animation.KeyFrames.Add(new LinearColorKeyFrame(Spectrum(hue, saturation, brightness), KeyTime.FromTimeSpan(TimeSpan.FromSeconds(t * value.Seconds))));
                }
                Timeline.SetDesiredFrameRate(animation, 20);
                brush.BeginAnimation(SolidColorBrush.ColorProperty, animation);
            }
        }
        public static string ModeOf(ColorSetting value)
        {
            return new[] { "static", "breathe", "rainbow", "reverse", "wave" }.Contains(value.Mode)
                ? value.Mode : value.Breathe ? "breathe" : "static";
        }
        static Color Spectrum(double hue, double saturation, double brightness)
        {
            double h = (hue % 1 + 1) % 1 * 6, x = 1 - Math.Abs(h % 2 - 1);
            double[] rgb = h < 1 ? new[] { 1.0, x, 0 } : h < 2 ? new[] { x, 1.0, 0 } : h < 3 ? new[] { 0, 1.0, x }
                : h < 4 ? new[] { 0, x, 1.0 } : h < 5 ? new[] { x, 0, 1.0 } : new[] { 1.0, 0, x };
            return Color.FromRgb((byte)Math.Round((rgb[0] * saturation + 1 - saturation) * brightness * 255),
                (byte)Math.Round((rgb[1] * saturation + 1 - saturation) * brightness * 255),
                (byte)Math.Round((rgb[2] * saturation + 1 - saturation) * brightness * 255));
        }
        public Brush PreviewBrush(string key) { return brushes[key]; }
        public void Save()
        {
            string temporary = path + ".tmp";
            File.WriteAllText(temporary, new JavaScriptSerializer().Serialize(Values));
            if (File.Exists(path)) File.Replace(temporary, path, null); else File.Move(temporary, path);
        }
        public AppearanceEditor CreateEditor() { return new AppearanceEditor(owner, this); }
    }

    sealed class AppearanceEditor : UserControl
    {
        readonly Appearance theme;
        Dictionary<string, ColorSetting> original;
        readonly StackPanel body = new StackPanel();
        readonly TextBlock heading = new TextBlock { FontSize = 23 };
        readonly TextBlock message = new TextBlock { TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 8, 0, 8) };
        readonly Border sample = new Border { Height = 45, CornerRadius = new CornerRadius(8), Margin = new Thickness(0, 8, 0, 10) };
        readonly Slider[] rgb = new Slider[3];
        readonly TextBlock[] numbers = new TextBlock[3];
        readonly TextBox hex = new TextBox { Padding = new Thickness(10), Margin = new Thickness(0, 6, 0, 8), MaxLength = 7 };
        readonly ComboBox mode = new ComboBox { Margin = new Thickness(0, 10, 0, 10), ItemsSource = new[] { "Постоянный цвет", "Дыхание — два цвета", "Радуга", "Радуга — обратно", "Волна — оттенки и яркость" } };
        static readonly string[] modes = { "static", "breathe", "rainbow", "reverse", "wave" };
        readonly Slider speed = new Slider { Minimum = 2, Maximum = 12, Value = 4, TickFrequency = 0.5, IsSnapToTickEnabled = true };
        readonly TextBlock speedText = new TextBlock { Margin = new Thickness(0, 6, 0, 12) };
        readonly Button first, second;
        readonly Dictionary<string, Button> selectors = new Dictionary<string, Button>();
        string key = "Panel";
        bool editingSecond, syncing;
        public AppearanceEditor(Window owner, Appearance theme)
        {
            this.theme = theme; original = theme.Copy();
            SetResourceReference(BackgroundProperty, "ThemePanel");
            SetResourceReference(ForegroundProperty, "ThemeText");
            FontFamily = new FontFamily("Segoe UI"); FontSize = 14;
            message.SetResourceReference(TextBlock.ForegroundProperty, "ThemeMuted");
            hex.SetResourceReference(BackgroundProperty, "ThemeButton");
            hex.SetResourceReference(ForegroundProperty, "ThemeText");
            hex.SetResourceReference(BorderBrushProperty, "ThemeButtonBorder");
            hex.SetResourceReference(TextBox.CaretBrushProperty, "ThemeAccent");
            Resources[typeof(Button)] = owner.Resources[typeof(Button)];
            Resources[typeof(Slider)] = owner.Resources[typeof(Slider)];
            Resources[typeof(CheckBox)] = owner.Resources[typeof(CheckBox)];
            Resources[typeof(ComboBox)] = owner.Resources[typeof(ComboBox)];
            Resources[typeof(ComboBoxItem)] = owner.Resources[typeof(ComboBoxItem)];
            Resources[typeof(System.Windows.Controls.Primitives.ScrollBar)] = owner.Resources[typeof(System.Windows.Controls.Primitives.ScrollBar)];
            Resources["ScrollPage"] = owner.Resources["ScrollPage"];
            // Inherit the live theme brushes from the main window, including animations.
            var layout = new Grid { Margin = new Thickness(12) };
            layout.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(225) });
            layout.ColumnDefinitions.Add(new ColumnDefinition());
            var items = new StackPanel();
            foreach (var part in Appearance.Parts) {
                string id = part[0]; var button = MakeButton(part[1], delegate { key = id; Sync(); });
                button.HorizontalContentAlignment = HorizontalAlignment.Left; selectors[id] = button; items.Children.Add(button);
            }
            layout.Children.Add(new ScrollViewer { Content = items, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled, Margin = new Thickness(0, 0, 16, 0) });
            var scroll = new ScrollViewer { Content = body, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled };
            Grid.SetColumn(scroll, 1); layout.Children.Add(scroll); Content = layout;
            body.Children.Add(heading);
            body.Children.Add(Hint("Изменения сразу видны на панели и в этой вкладке.\nВыберите деталь слева, затем её цвет."));
            var channels = new WrapPanel();
            first = MakeButton("Основной цвет", delegate { editingSecond = false; Sync(); });
            second = MakeButton("Второй цвет", delegate { editingSecond = true; Sync(); });
            channels.Children.Add(first); channels.Children.Add(second); body.Children.Add(channels);
            var spectrum = new Border { Height = 38, CornerRadius = new CornerRadius(6), Margin = new Thickness(0, 4, 0, 10), Cursor = Cursors.Cross };
            var gradient = new LinearGradientBrush { StartPoint = new Point(0, 0), EndPoint = new Point(1, 0) };
            Color[] rainbow = { Colors.Red, Colors.Yellow, Colors.Lime, Colors.Cyan, Colors.Blue, Colors.Magenta, Colors.Red };
            for (int i = 0; i < rainbow.Length; i++) gradient.GradientStops.Add(new GradientStop(rainbow[i], i / 6.0));
            spectrum.Background = gradient;
            Action<MouseEventArgs> pick = e => {
                double hue = Math.Max(0, Math.Min(5.999, e.GetPosition(spectrum).X / spectrum.ActualWidth * 6));
                int i = (int)hue; double mix = hue - i;
                SetColor(Color.FromRgb((byte)(rainbow[i].R * (1-mix) + rainbow[i+1].R * mix), (byte)(rainbow[i].G * (1-mix) + rainbow[i+1].G * mix), (byte)(rainbow[i].B * (1-mix) + rainbow[i+1].B * mix)));
            };
            spectrum.MouseLeftButtonDown += delegate(object s, MouseButtonEventArgs e) { spectrum.CaptureMouse(); pick(e); };
            spectrum.MouseMove += delegate(object s, MouseEventArgs e) { if (spectrum.IsMouseCaptured) pick(e); };
            spectrum.MouseLeftButtonUp += delegate { spectrum.ReleaseMouseCapture(); };
            body.Children.Add(spectrum);
            var presets = new WrapPanel();
            foreach (Color preset in new[] { Colors.Red, Colors.Lime, Colors.Blue, Colors.Magenta, Colors.Orange, Colors.Cyan, Colors.Yellow, Colors.White, Colors.Black }) {
                Color selected = preset;
                var button = MakeButton("", delegate { SetColor(selected); });
                button.Width = 38; button.Height = 29; button.Padding = new Thickness(0); button.Background = new SolidColorBrush(preset); button.ToolTip = preset.ToString(); presets.Children.Add(button);
            }
            body.Children.Add(presets); body.Children.Add(sample);
            for (int i = 0; i < 3; i++) {
                var row = new DockPanel { Margin = new Thickness(0, 6, 0, 6) };
                row.Children.Add(new TextBlock { Text = new[] { "R", "G", "B" }[i], Width = 25 });
                numbers[i] = new TextBlock { Width = 34, TextAlignment = TextAlignment.Right }; DockPanel.SetDock(numbers[i], Dock.Right); row.Children.Add(numbers[i]);
                rgb[i] = new Slider { Minimum = 0, Maximum = 255, TickFrequency = 1, IsSnapToTickEnabled = true };
                rgb[i].Foreground = new[] { Brushes.IndianRed, Brushes.LightGreen, Brushes.CornflowerBlue }[i];
                rgb[i].ValueChanged += delegate { if (!syncing) SetColor(Color.FromRgb((byte)rgb[0].Value, (byte)rgb[1].Value, (byte)rgb[2].Value)); };
                row.Children.Add(rgb[i]); body.Children.Add(row);
            }
            body.Children.Add(hex);
            hex.KeyDown += delegate(object s, KeyEventArgs e) { if (e.Key == Key.Enter) { CommitHex(); e.Handled = true; } };
            hex.LostKeyboardFocus += delegate { CommitHex(); };
            body.Children.Add(mode);
            mode.SelectionChanged += delegate { if (!syncing && mode.SelectedIndex >= 0) {
                theme.Values[key].Mode = modes[mode.SelectedIndex];
                theme.Values[key].Breathe = mode.SelectedIndex == 1;
                theme.Apply(key); Sync();
            } };
            body.Children.Add(speed); body.Children.Add(speedText);
            speed.ValueChanged += delegate { if (!syncing) { theme.Values[key].Seconds = speed.Value; theme.Apply(key); speedText.Text = "Полный цикл: " + speed.Value.ToString("0.0") + " с"; } };
            body.Children.Add(Hint("Дыхание — между двумя цветами. Радуга — спектр по кругу. Волна — ещё и светлые / тёмные оттенки. При сворачивании анимация останавливается."));
            body.Children.Add(message);
            var actions = new WrapPanel();
            actions.Children.Add(MakeButton("По умолчанию", delegate { ResetSelected(); }));
            actions.Children.Add(MakeButton("Отмена", delegate { Cancel(); }));
            actions.Children.Add(MakeButton("Сохранить", delegate {
                if (!CommitHex()) return;
                try { theme.Save(); original = theme.Copy(); message.Text = "Оформление сохранено."; } catch (Exception ex) { message.Text = "Не удалось сохранить: " + ex.Message; }
            }));
            body.Children.Add(actions);
            Sync();
        }
        public void ResetSelected()
        {
            theme.Values[key] = Appearance.Defaults()[key];
            theme.Apply(key);
            Sync();
            message.Text = "Сброшена только выбранная деталь. Для записи нажмите «Сохранить».";
        }
        public void Cancel() { theme.Values = new JavaScriptSerializer().Deserialize<Dictionary<string, ColorSetting>>(new JavaScriptSerializer().Serialize(original)); theme.Apply(); Sync(); }
        TextBlock Hint(string text)
        {
            var block = new TextBlock { Text = text, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 8, 0, 10) };
            block.SetResourceReference(TextBlock.ForegroundProperty, "ThemeMuted");
            return block;
        }
        Button MakeButton(string text, Action action)
        {
            var button = new Button { Content = text, Margin = new Thickness(0, 0, 8, 8), Padding = new Thickness(10, 8, 10, 8) };
            button.Click += delegate { action(); }; return button;
        }
        bool CommitHex()
        {
            if (syncing) return true;
            Color c;
            if (!Appearance.TryColor(hex.Text.Trim(), out c)) { message.Text = "HEX: шесть цифр после #, например #83D9A3."; return false; }
            SetColor(c); return true;
        }
        void SetColor(Color color)
        {
            if (editingSecond) theme.Values[key].Second = "#" + color.R.ToString("X2") + color.G.ToString("X2") + color.B.ToString("X2");
            else theme.Values[key].First = "#" + color.R.ToString("X2") + color.G.ToString("X2") + color.B.ToString("X2");
            theme.Apply(key); Sync();
        }
        void Sync()
        {
            syncing = true;
            var value = theme.Values[key];
            heading.Text = Appearance.Parts.First(p => p[0] == key)[1];
            var color = (Color)ColorConverter.ConvertFromString(editingSecond ? value.Second : value.First);
            rgb[0].Value = color.R; rgb[1].Value = color.G; rgb[2].Value = color.B;
            for (int i = 0; i < 3; i++) numbers[i].Text = rgb[i].Value.ToString("0");
            hex.Text = editingSecond ? value.Second : value.First;
            sample.Background = theme.PreviewBrush(key);
            mode.SelectedIndex = Array.IndexOf(modes, Appearance.ModeOf(value)); speed.Value = value.Seconds;
            speedText.Text = "Полный цикл: " + value.Seconds.ToString("0.0") + " с";
            first.SetResourceReference(BorderBrushProperty, editingSecond ? "ThemeButtonBorder" : "ThemeAccent");
            second.SetResourceReference(BorderBrushProperty, editingSecond ? "ThemeAccent" : "ThemeButtonBorder");
            foreach (var pair in selectors) pair.Value.SetResourceReference(BorderBrushProperty, pair.Key == key ? "ThemeAccent" : "ThemeButtonBorder");
            message.Text = "Предпросмотр без сохранения. Отмена вернёт прежние цвета.";
            syncing = false;
        }
    }
}
