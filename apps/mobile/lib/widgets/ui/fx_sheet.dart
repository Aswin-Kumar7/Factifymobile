/// A bottom sheet (v5): radius 28 at the top, a grabber, a dimmed scrim.
library;

import 'package:flutter/material.dart';

import '../../theme/tokens.dart';

Future<T?> showFxSheet<T>(
  BuildContext context, {
  required WidgetBuilder builder,
  EdgeInsetsGeometry padding = const EdgeInsets.fromLTRB(20, 0, 20, 18),
}) {
  final k = FactifyTokens.of(context);
  return showModalBottomSheet<T>(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    backgroundColor: k.sf,
    barrierColor: const Color.fromRGBO(5, 8, 6, .45),
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
    ),
    builder: (context) => SafeArea(
      top: false,
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Center(
              child: Container(
                width: 40,
                height: 4,
                margin: const EdgeInsets.fromLTRB(0, 10, 0, 14),
                decoration: BoxDecoration(
                  color: FactifyTokens.of(context).line,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
            Padding(padding: padding, child: builder(context)),
          ],
        ),
      ),
    ),
  );
}
