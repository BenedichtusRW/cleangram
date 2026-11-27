import 'package:flutter_test/flutter_test.dart';
import 'package:cleangram/main.dart';

void main() {
  testWidgets('CleanGramApp renders login screen', (WidgetTester tester) async {
    await tester.pumpWidget(const CleanGramApp());
    expect(find.text('Masuk ke CleanGram'), findsOneWidget);
    expect(find.text('ben_dev'), findsNothing); // RichText TextSpan sanity check
    expect(find.text('01 Login'), findsOneWidget);
    expect(find.text('Mobile v1.1'), findsOneWidget);
    expect(find.text('Blokir Bot opsional'), findsOneWidget);
    expect(find.text('☕ Support'), findsOneWidget);
  });
}
