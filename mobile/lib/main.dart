import 'package:flutter/material.dart';
import 'screens/home_screen.dart';

void main() {
  runApp(const CleanGramApp());
}

class CleanGramApp extends StatelessWidget {
  const CleanGramApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'CleanGram',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        brightness: Brightness.dark,
        scaffoldBackgroundColor: kBgColor,
        colorScheme: const ColorScheme.dark(
          primary: kTgBlue,
          surface: kCardColor,
        ),
      ),
      home: const HomeScreen(),
    );
  }
}
