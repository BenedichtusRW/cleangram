import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/dialog_item.dart';

class CleanGramApiException implements Exception {
  final String message;
  const CleanGramApiException(this.message);

  @override
  String toString() => message;
}

class CleanGramApi {
  static const String defaultBaseUrl = 'https://cleangram-alpha.vercel.app';
  String baseUrl;

  CleanGramApi({this.baseUrl = defaultBaseUrl});

  Uri _endpoint(String path) {
    final cleanBase = baseUrl.trim().replaceAll(RegExp(r'/+$'), '');
    return Uri.parse('$cleanBase$path');
  }

  Future<Map<String, dynamic>> _postJson(
    String path,
    Map<String, dynamic> body, {
    Duration timeout = const Duration(seconds: 35),
  }) async {
    late http.Response response;
    try {
      response = await http
          .post(
            _endpoint(path),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(body),
          )
          .timeout(timeout);
    } catch (e) {
      throw CleanGramApiException(
        'Gagal terhubung ke server CleanGram. Periksa koneksi internet Anda ($e).',
      );
    }

    Map<String, dynamic> decoded;
    try {
      decoded = jsonDecode(response.body) as Map<String, dynamic>;
    } catch (_) {
      throw CleanGramApiException(
        'Respon server tidak valid (HTTP ${response.statusCode}).',
      );
    }

    if (response.statusCode < 200 || response.statusCode >= 300) {
      final detail = decoded['detail']?.toString();
      throw CleanGramApiException(
        detail ?? 'Permintaan gagal (HTTP ${response.statusCode}).',
      );
    }
    return decoded;
  }

  Future<({String flowToken, String phone, String delivery})> sendCode({
    required String phone,
    int? customApiId,
    String? customApiHash,
  }) async {
    final data = await _postJson('/api/send-code', {
      'phone': phone,
      'custom_api_id': customApiId,
      'custom_api_hash': (customApiHash != null && customApiHash.isNotEmpty)
          ? customApiHash
          : null,
    });
    return (
      flowToken: data['flow_token'] as String,
      phone: (data['phone'] as String?) ?? phone,
      delivery: (data['delivery'] as String?) ?? 'Aplikasi Telegram',
    );
  }

  Future<ScanResult> verifyScan({
    required String flowToken,
    String? code,
    String? password,
    String whitelist = '',
  }) async {
    final data = await _postJson('/api/verify-scan', {
      'flow_token': flowToken,
      'code': (code != null && code.isNotEmpty) ? code : null,
      'password': (password != null && password.isNotEmpty) ? password : null,
      'whitelist': whitelist,
    });
    return ScanResult.fromJson(data);
  }

  Future<({String flowToken, String qrUrl})> qrStart({
    int? customApiId,
    String? customApiHash,
  }) async {
    final data = await _postJson('/api/qr-start', {
      'custom_api_id': customApiId,
      'custom_api_hash': (customApiHash != null && customApiHash.isNotEmpty)
          ? customApiHash
          : null,
    });
    return (
      flowToken: data['flow_token'] as String,
      qrUrl: data['qr_url'] as String,
    );
  }

  Future<({String status, String flowToken, String? qrUrl, ScanResult? scan})>
      qrCheck({
    required String flowToken,
    String whitelist = '',
  }) async {
    final data = await _postJson('/api/qr-check', {
      'flow_token': flowToken,
      'whitelist': whitelist,
    });
    final status = (data['status'] as String?) ?? 'pending';
    final nextToken = (data['flow_token'] as String?) ?? flowToken;
    if (status == 'scanned' || status == '2fa_required') {
      return (
        status: status,
        flowToken: nextToken,
        qrUrl: null,
        scan: ScanResult.fromJson(data),
      );
    }
    return (
      status: status,
      flowToken: nextToken,
      qrUrl: data['qr_url'] as String?,
      scan: null,
    );
  }

  Future<BatchCleanResult> cleanBatch({
    required String flowToken,
    required List<int> targetIds,
    required bool isLastBatch,
    required bool autoLogout,
  }) async {
    final data = await _postJson(
      '/api/clean-batch',
      {
        'flow_token': flowToken,
        'target_ids': targetIds,
        'is_last_batch': isLastBatch,
        'auto_logout': autoLogout,
      },
      timeout: const Duration(seconds: 60),
    );
    return BatchCleanResult.fromJson(data);
  }

  Future<void> logout(String flowToken) async {
    try {
      await _postJson(
        '/api/logout',
        {'flow_token': flowToken},
        timeout: const Duration(seconds: 10),
      );
    } catch (_) {
      // Abaikan kegagalan logout terbaik-usaha saat pembatalan
    }
  }
}
