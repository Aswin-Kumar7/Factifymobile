import 'package:factify_mobile/quick/bubble.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('The floating Factify button', () {
    test('turned on when drawing is allowed, it shows at once', () async {
      final phone = NoBubble(allowed: true);
      final bubble = BubbleController.inMemory(platform: phone);

      await bubble.choose(true);

      expect(bubble.on, isTrue);
      expect(phone.showing, isTrue);
      expect(phone.asked, 0);
    });

    test('turned on without permission, Settings opens to allow it', () async {
      final phone = NoBubble();
      final bubble = BubbleController.inMemory(platform: phone);

      await bubble.choose(true);

      expect(phone.asked, 1);
      expect(phone.showing, isFalse);
    });

    test('back from Settings having allowed it, the button appears', () async {
      final phone = NoBubble();
      final bubble = BubbleController.inMemory(platform: phone);
      await bubble.choose(true);

      phone.allowed = true;
      await bubble.sync();

      expect(bubble.on, isTrue);
      expect(phone.showing, isTrue);
    });

    test('back from Settings without allowing it, the switch goes off', () async {
      final phone = NoBubble();
      final bubble = BubbleController.inMemory(platform: phone);
      await bubble.choose(true);

      await bubble.sync();

      expect(bubble.on, isFalse);
      expect(phone.showing, isFalse);
    });

    test('turned off, the button goes away', () async {
      final phone = NoBubble(allowed: true);
      final bubble = BubbleController.inMemory(platform: phone);
      await bubble.choose(true);

      await bubble.choose(false);

      expect(bubble.on, isFalse);
      expect(phone.showing, isFalse);
    });
  });
}
