/// The floating Factify button (Profile -> "Floating Factify button").
///
/// WhatsApp gives a text message no Share button, so a text forward could not be
/// shared to Factify at all. With this on, a small Factify button floats over every
/// app: copy the message, tap the button, and the answer opens over the chat
/// (FactifyBubbleService, QuickVerdictActivity). Like Google Translate's Tap to
/// Translate, it needs "display over other apps", which the person grants once in
/// Settings.
///
/// Off by default. The choice is remembered on this phone; the button is started
/// again when the app opens, so it survives the phone restarting.
library;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// What the phone can do about the button.
abstract class BubblePlatform {
  /// Whether Factify may draw over other apps.
  Future<bool> canDraw();

  /// Opens the Settings page where that is allowed.
  Future<void> askToDraw();

  /// Shows the button; false when it may not be drawn.
  Future<bool> start();

  Future<void> stop();
}

/// FactifyBubbleService, over the `factify/bubble` channel (MainActivity).
class BubbleChannel implements BubblePlatform {
  static const MethodChannel _channel = MethodChannel('factify/bubble');

  @override
  Future<bool> canDraw() async => await _call<bool>('canDraw') ?? false;

  @override
  Future<void> askToDraw() => _call<void>('askToDraw');

  @override
  Future<bool> start() async => await _call<bool>('start') ?? false;

  @override
  Future<void> stop() => _call<void>('stop');

  Future<T?> _call<T>(String method) async {
    try {
      return await _channel.invokeMethod<T>(method);
    } on PlatformException {
      return null;
    } on MissingPluginException {
      return null;
    }
  }
}

/// For tests, and anywhere the button does not exist: nothing can be drawn.
class NoBubble implements BubblePlatform {
  NoBubble({this.allowed = false});

  bool allowed;
  bool showing = false;
  int asked = 0;

  @override
  Future<bool> canDraw() async => allowed;

  @override
  Future<void> askToDraw() async => asked++;

  @override
  Future<bool> start() async => showing = allowed;

  @override
  Future<void> stop() async => showing = false;
}

/// Whether the button is wanted, and keeping the phone in step with that.
class BubbleController extends ChangeNotifier with WidgetsBindingObserver {
  BubbleController._(this._platform, this._store, this._on);

  /// The saved choice, with the button started if it is on and allowed.
  static Future<BubbleController> load({BubblePlatform? platform}) async {
    SharedPreferencesAsync? store;
    var on = false;
    try {
      store = SharedPreferencesAsync();
      on = await store.getBool(_key) ?? false;
    } on Object {
      store = null;
    }
    final controller = BubbleController._(platform ?? BubbleChannel(), store, on);
    WidgetsBinding.instance.addObserver(controller);
    await controller.sync();
    return controller;
  }

  /// Never written anywhere - for tests.
  factory BubbleController.inMemory({BubblePlatform? platform, bool on = false}) =>
      BubbleController._(platform ?? NoBubble(), null, on);

  static const String _key = 'floating_button';

  final BubblePlatform _platform;
  final SharedPreferencesAsync? _store;
  bool _on;

  /// Settings was opened to allow drawing, and we are waiting to hear back.
  bool _asking = false;

  bool get on => _on;

  /// Turned on: shown at once when allowed, else Settings opens to allow it and the
  /// button appears when the person comes back having allowed it.
  Future<void> choose(bool on) async {
    if (!on) {
      _asking = false;
      await _platform.stop();
      await _save(false);
      return;
    }
    if (await _platform.canDraw()) {
      await _save(await _platform.start());
      return;
    }
    _asking = true;
    await _save(true);
    await _platform.askToDraw();
  }

  /// The phone made to match the choice: on and allowed is showing; on but no
  /// longer allowed (or not allowed after asking) is turned off.
  Future<void> sync() async {
    if (!_on) return;
    if (await _platform.canDraw()) {
      _asking = false;
      await _platform.start();
    } else {
      _asking = false;
      await _save(false);
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Back from Settings (or anywhere): show or drop the button to match.
    if (state == AppLifecycleState.resumed && (_on || _asking)) sync();
  }

  Future<void> _save(bool on) async {
    if (_on != on) {
      _on = on;
      notifyListeners();
    }
    try {
      await _store?.setBool(_key, on);
    } on Object {
      // Still applied for this session; only remembering it failed.
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }
}
