import 'dart:async';
import 'package:flutter/material.dart';
import 'package:qr_flutter/qr_flutter.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/dialog_item.dart';
import '../services/cleangram_api.dart';

const Color kBgColor = Color(0xFF09090B);
const Color kCardColor = Color(0xFF111114);
const Color kBorderColor = Color(0xFF27272A);
const Color kTgBlue = Color(0xFF24A1DE);
const Color kEmerald = Color(0xFF10B981);
const Color kDanger = Color(0xFFDC2626);

class _LogLine {
  final String text;
  final Color color;
  const _LogLine(this.text, this.color);
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final CleanGramApi _api = CleanGramApi();

  int _step = 1;
  bool _useQrMode = false;
  bool _isBusy = false;
  bool _isCleaningActive = false;
  bool _cleaningDone = false;
  String? _errorMsg;

  // Step 1 & 2 state
  String? _flowToken;
  String _displayPhone = '';
  String _deliveryInfo = 'Aplikasi Telegram';
  bool _requires2FA = false;
  bool _hideOtpFor2FA = false;
  String? _qrUrl;
  Timer? _qrTimer;

  // Controllers
  final _phoneCtrl = TextEditingController();
  final _otpCtrl = TextEditingController();
  final _twoFaCtrl = TextEditingController();
  final _whitelistCtrl = TextEditingController();
  final _apiIdCtrl = TextEditingController();
  final _apiHashCtrl = TextEditingController();
  final _serverUrlCtrl =
      TextEditingController(text: CleanGramApi.defaultBaseUrl);
  final _searchCtrl = TextEditingController();

  // Step 3 state
  UserSummary? _user;
  List<DialogTarget> _targets = [];
  List<ProtectedItem> _protectedItems = [];
  Set<int> _selectedIds = {};
  bool _showProtectedTab = false;
  String _categoryFilter = 'ALL';
  bool _blockBots = false;
  bool _autoLogout = true;

  // Step 4 state
  double _progress = 0.0;
  int _totalSuccess = 0;
  int _totalFailed = 0;
  final List<_LogLine> _logs = [];
  final ScrollController _logScrollCtrl = ScrollController();

  @override
  void dispose() {
    _stopQrTimer();
    _phoneCtrl.dispose();
    _otpCtrl.dispose();
    _twoFaCtrl.dispose();
    _whitelistCtrl.dispose();
    _apiIdCtrl.dispose();
    _apiHashCtrl.dispose();
    _serverUrlCtrl.dispose();
    _searchCtrl.dispose();
    _logScrollCtrl.dispose();
    super.dispose();
  }

  void _stopQrTimer() {
    _qrTimer?.cancel();
    _qrTimer = null;
  }

  Future<void> _openExternalUrl(String url) async {
    final uri = Uri.parse(url);
    await launchUrl(uri, mode: LaunchMode.externalApplication);
  }

  (int?, String?) _readDeveloperCreds() {
    final customServer = _serverUrlCtrl.text.trim();
    _api.baseUrl =
        customServer.isNotEmpty ? customServer : CleanGramApi.defaultBaseUrl;

    final rawId = _apiIdCtrl.text.trim();
    final apiId = rawId.isNotEmpty ? int.tryParse(rawId) : null;
    final apiHash = _apiHashCtrl.text.trim();
    return (apiId, apiHash.isNotEmpty ? apiHash : null);
  }

  void _showError(String msg) {
    setState(() {
      _errorMsg = msg;
    });
  }

  Future<void> _resetToStep1({bool callLogout = true}) async {
    _stopQrTimer();
    final token = _flowToken;
    setState(() {
      _flowToken = null;
      _qrUrl = null;
      _requires2FA = false;
      _hideOtpFor2FA = false;
      _errorMsg = null;
      _otpCtrl.clear();
      _twoFaCtrl.clear();
      _step = 1;
    });
    if (callLogout && token != null) {
      await _api.logout(token);
    }
  }

  // ---- OTP FLOW ----
  Future<void> _handleSendOtp() async {
    final phone = _phoneCtrl.text.trim();
    if (phone.length < 6) {
      _showError('Masukkan nomor HP Telegram yang valid (+628... atau 08...).');
      return;
    }

    final (apiId, apiHash) = _readDeveloperCreds();
    setState(() {
      _isBusy = true;
      _errorMsg = null;
    });

    try {
      final res = await _api.sendCode(
        phone: phone,
        customApiId: apiId,
        customApiHash: apiHash,
      );
      if (!mounted) return;
      setState(() {
        _flowToken = res.flowToken;
        _displayPhone = res.phone;
        _deliveryInfo = res.delivery;
        _requires2FA = false;
        _hideOtpFor2FA = false;
        _step = 2;
      });
    } catch (e) {
      if (mounted) _showError(e.toString());
    } finally {
      if (mounted) setState(() => _isBusy = false);
    }
  }

  Future<void> _handleVerifyScan() async {
    if (_flowToken == null) return;
    setState(() {
      _isBusy = true;
      _errorMsg = null;
    });

    try {
      final res = await _api.verifyScan(
        flowToken: _flowToken!,
        code: _hideOtpFor2FA ? null : _otpCtrl.text.trim(),
        password: _twoFaCtrl.text.isNotEmpty ? _twoFaCtrl.text : null,
        whitelist: _whitelistCtrl.text.trim(),
      );
      if (!mounted) return;

      if (res.status == '2fa_required') {
        setState(() {
          _flowToken = res.flowToken;
          _requires2FA = true;
          _hideOtpFor2FA = true;
        });
        return;
      }

      _applyScanResult(res);
    } catch (e) {
      if (mounted) _showError(e.toString());
    } finally {
      if (mounted) setState(() => _isBusy = false);
    }
  }

  // ---- QR FLOW ----
  Future<void> _handleStartQr() async {
    _stopQrTimer();
    final (apiId, apiHash) = _readDeveloperCreds();
    setState(() {
      _isBusy = true;
      _errorMsg = null;
    });

    try {
      final res = await _api.qrStart(
        customApiId: apiId,
        customApiHash: apiHash,
      );
      if (!mounted) return;
      setState(() {
        _flowToken = res.flowToken;
        _qrUrl = res.qrUrl;
      });
      _scheduleQrPoll();
    } catch (e) {
      if (mounted) _showError(e.toString());
    } finally {
      if (mounted) setState(() => _isBusy = false);
    }
  }

  void _scheduleQrPoll() {
    _stopQrTimer();
    _qrTimer = Timer(const Duration(milliseconds: 2500), _pollQrOnce);
  }

  Future<void> _pollQrOnce() async {
    if (!mounted || _qrUrl == null || _flowToken == null || _step != 1) return;

    try {
      final res = await _api.qrCheck(
        flowToken: _flowToken!,
        whitelist: _whitelistCtrl.text.trim(),
      );
      if (!mounted) return;

      if (res.status == '2fa_required' && res.scan != null) {
        _stopQrTimer();
        setState(() {
          _qrUrl = null;
          _flowToken = res.flowToken;
          _requires2FA = true;
          _hideOtpFor2FA = true;
          _displayPhone = 'QR Login';
          _deliveryInfo = 'Verifikasi 2FA';
          _step = 2;
        });
        return;
      }

      if (res.status == 'scanned' && res.scan != null) {
        _stopQrTimer();
        setState(() => _qrUrl = null);
        _applyScanResult(res.scan!);
        return;
      }

      setState(() {
        _flowToken = res.flowToken;
        if (res.qrUrl != null) _qrUrl = res.qrUrl;
      });
      _scheduleQrPoll();
    } catch (e) {
      if (!mounted) return;
      _stopQrTimer();
      setState(() => _qrUrl = null);
      _showError(e.toString());
    }
  }

  void _applyScanResult(ScanResult res) {
    setState(() {
      _flowToken = res.flowToken;
      _user = res.user;
      _targets = res.targets;
      _protectedItems = res.protectedItems;
      _selectedIds = res.targets.map((e) => e.id).toSet();
      _showProtectedTab = false;
      _categoryFilter = 'ALL';
      _blockBots = false;
      _searchCtrl.clear();
      _errorMsg = null;
      _step = 3;
    });
  }

  // ---- BATCH CLEANUP ----
  Future<void> _confirmAndClean() async {
    final ids = _selectedIds.toList();
    if (ids.isEmpty || _flowToken == null) return;

    final botNote = _blockBots
        ? 'Bot yang tercentang juga akan diblokir permanen agar tidak mengirim spam lagi. Grup & Saluran tetap keluar bersih.'
        : 'Kontak HP & grup yang dilindungi tetap 100% aman. Tidak ada pemblokiran akun.';

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: kCardColor,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: const BorderSide(color: kBorderColor),
        ),
        title: const Text(
          'Konfirmasi Pembersihan',
          style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
        ),
        content: Text(
          'Yakin ingin KELUAR & HAPUS RIWAYAT ${ids.length} grup/saluran/bot terpilih?\n\n$botNote',
          style: const TextStyle(fontSize: 13, color: Colors.white70),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Batal', style: TextStyle(color: Colors.white60)),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(backgroundColor: kDanger),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Ya, Bersihkan',
                style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );

    if (confirmed == true) {
      await _runCleanBatches(ids);
    }
  }

  void _appendLog(String msg, Color color) {
    setState(() {
      _logs.add(_LogLine(msg, color));
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_logScrollCtrl.hasClients) {
        _logScrollCtrl.animateTo(
          _logScrollCtrl.position.maxScrollExtent,
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOut,
        );
      }
    });
  }

  Future<void> _runCleanBatches(List<int> queue) async {
    const int batchSize = 15;
    final total = queue.length;
    int processed = 0;
    int cursor = 0;
    final bool blockBots = _blockBots;

    setState(() {
      _step = 4;
      _isCleaningActive = true;
      _cleaningDone = false;
      _progress = 0.0;
      _totalSuccess = 0;
      _totalFailed = 0;
      _logs.clear();
      _errorMsg = null;
    });

    _appendLog(
      '[MEMULAI] Memproses $total target (${blockBots ? "dengan blokir Bot spam" : "tanpa blokir"})...',
      kTgBlue,
    );

    try {
      while (cursor < total) {
        final end = (cursor + batchSize).clamp(0, total);
        final batchIds = queue.sublist(cursor, end);
        final isLastBatch = end >= total;

        final res = await _api.cleanBatch(
          flowToken: _flowToken!,
          targetIds: batchIds,
          isLastBatch: isLastBatch,
          autoLogout: _autoLogout,
          blockBots: blockBots,
        );
        if (!mounted) return;

        for (final item in res.results) {
          processed++;
          setState(() {
            _progress = processed / total;
            if (item.status == 'ok') {
              _totalSuccess++;
            } else {
              _totalFailed++;
            }
          });
          if (item.status == 'ok') {
            _appendLog(
              '✓ [$processed/$total] ${item.name} (${item.type}) — ${item.message}',
              kEmerald,
            );
          } else {
            _appendLog(
              '✗ [$processed/$total] Dilewati: ${item.name} — ${item.message}',
              Colors.amber,
            );
          }
        }

        cursor += res.results.length;

        if (res.floodwaitSeconds > 0) {
          _appendLog(
            '⏳ [Limit Telegram] Menunggu ${res.floodwaitSeconds} detik...',
            Colors.amberAccent,
          );
          await Future.delayed(Duration(seconds: res.floodwaitSeconds));
          continue;
        }

        if (res.results.isEmpty) {
          cursor += batchIds.length;
        }
      }

      if (!mounted) return;
      setState(() {
        _progress = 1.0;
        _cleaningDone = true;
        _flowToken = null;
      });
    } catch (e) {
      if (mounted) {
        _showError(e.toString());
        _appendLog('❌ Koneksi terputus: $e', Colors.redAccent);
      }
    } finally {
      if (mounted) setState(() => _isCleaningActive = false);
    }
  }

  // ---- UI BUILD ----
  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: !_isCleaningActive,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop && _isCleaningActive) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text(
                'Pembersihan sedang berjalan, tunggu hingga selesai agar sesi ter-logout otomatis.',
              ),
            ),
          );
        }
      },
      child: Scaffold(
        backgroundColor: kBgColor,
        appBar: _buildAppBar(),
        body: SafeArea(
          child: Column(
            children: [
              _buildStepBar(),
              if (_errorMsg != null) _buildErrorBanner(),
              Expanded(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 20),
                  child: _buildCurrentStep(),
                ),
              ),
              _buildFooter(),
            ],
          ),
        ),
      ),
    );
  }

  PreferredSizeWidget _buildAppBar() {
    return AppBar(
      backgroundColor: kBgColor,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      bottom: PreferredSize(
        preferredSize: const Size.fromHeight(1),
        child: Container(height: 1, color: kBorderColor),
      ),
      title: Row(
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(8),
            child: Image.asset('assets/logo.png', width: 30, height: 30),
          ),
          const SizedBox(width: 10),
          const Text(
            'CleanGram',
            style: TextStyle(
              fontSize: 17,
              fontWeight: FontWeight.w700,
              color: Colors.white,
            ),
          ),
          const SizedBox(width: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
            decoration: BoxDecoration(
              border: Border.all(color: kBorderColor),
              borderRadius: BorderRadius.circular(6),
            ),
            child: const Text(
              'Mobile',
              style: TextStyle(
                fontSize: 10,
                fontFamily: 'monospace',
                color: Colors.white54,
              ),
            ),
          ),
        ],
      ),
      actions: [
        Padding(
          padding: const EdgeInsets.only(right: 12),
          child: OutlinedButton.icon(
            style: OutlinedButton.styleFrom(
              foregroundColor: Colors.white70,
              side: const BorderSide(color: kBorderColor),
              backgroundColor: const Color(0xFF18181B),
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              minimumSize: Size.zero,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(8),
              ),
            ),
            onPressed: () =>
                _openExternalUrl('https://github.com/BenedichtusRW/cleangram'),
            icon: const Icon(Icons.code_rounded, size: 15),
            label: const Text('GitHub', style: TextStyle(fontSize: 12)),
          ),
        ),
      ],
    );
  }

  Widget _buildStepBar() {
    const labels = ['01 Login', '02 Verifikasi', '03 Target', '04 Selesai'];
    return Container(
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: kBorderColor)),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Row(
        children: List.generate(4, (idx) {
          final stepNum = idx + 1;
          final isDone = stepNum < _step;
          final isActive = stepNum == _step;
          final borderColor = isDone
              ? kEmerald
              : (isActive ? kTgBlue : Colors.transparent);
          final textColor = isDone
              ? kEmerald
              : (isActive ? Colors.white : Colors.white38);
          return Expanded(
            child: Container(
              padding: const EdgeInsets.symmetric(vertical: 11),
              decoration: BoxDecoration(
                border: Border(bottom: BorderSide(color: borderColor, width: 2)),
              ),
              child: Text(
                labels[idx],
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: isActive ? FontWeight.w700 : FontWeight.w500,
                  color: textColor,
                ),
              ),
            ),
          );
        }),
      ),
    );
  }

  Widget _buildErrorBanner() {
    return Container(
      margin: const EdgeInsets.fromLTRB(16, 12, 16, 0),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFF2B0F13),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.redAccent.withAlpha(120)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.error_outline, color: Colors.redAccent, size: 18),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              _errorMsg!,
              style: const TextStyle(fontSize: 12, color: Color(0xFFFECACA)),
            ),
          ),
          GestureDetector(
            onTap: () => setState(() => _errorMsg = null),
            child: const Icon(Icons.close, color: Colors.white54, size: 16),
          ),
        ],
      ),
    );
  }

  Widget _buildCurrentStep() {
    switch (_step) {
      case 1:
        return _buildStep1();
      case 2:
        return _buildStep2();
      case 3:
        return _buildStep3();
      default:
        return _buildStep4();
    }
  }

  InputDecoration _inputDeco(String hint) {
    return InputDecoration(
      hintText: hint,
      hintStyle: const TextStyle(color: Colors.white24, fontSize: 13),
      filled: true,
      fillColor: kBgColor,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 13),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: kBorderColor),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: kTgBlue),
      ),
    );
  }

  Widget _cardContainer({required List<Widget> children}) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: kCardColor,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: kBorderColor),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: children,
      ),
    );
  }

  Widget _buildWhitelistBox(TextEditingController ctrl) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        RichText(
          text: const TextSpan(
            style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
            children: [
              TextSpan(
                text: 'Grup / Channel / Bot yang ',
                style: TextStyle(color: Colors.white),
              ),
              TextSpan(
                text: 'DILINDUNGI (Jangan Dihapus)',
                style: TextStyle(color: kEmerald),
              ),
            ],
          ),
        ),
        const SizedBox(height: 5),
        const Text(
          'Ketik sebagian kata / nama grup penting agar otomatis diamankan (pisahkan koma). Contoh: ketik "keluarga" maka grup "Keluarga Besar" aman. Kontak HP otomatis aman. Boleh dikosongkan (bisa dipilih manual nanti).',
          style: TextStyle(fontSize: 11, color: Colors.white54, height: 1.4),
        ),
        const SizedBox(height: 8),
        TextField(
          controller: ctrl,
          style: const TextStyle(fontSize: 13, color: Colors.white),
          decoration: _inputDeco('Contoh: kampus, kantor, keluarga, crypto'),
        ),
      ],
    );
  }

  Widget _buildStep1() {
    return _cardContainer(
      children: [
        const Text(
          'Masuk ke CleanGram',
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: 20,
            fontWeight: FontWeight.w700,
            color: Colors.white,
          ),
        ),
        const SizedBox(height: 6),
        const Text(
          'Keluar dari grup spam, saluran asing, dan bot tanpa menyentuh kontak pribadi.',
          textAlign: TextAlign.center,
          style: TextStyle(fontSize: 12, color: Colors.white54),
        ),
        const SizedBox(height: 16),

        // Mode switcher (OTP vs QR)
        Container(
          padding: const EdgeInsets.all(4),
          decoration: BoxDecoration(
            color: kBgColor,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: kBorderColor),
          ),
          child: Row(
            children: [
              Expanded(
                child: _methodTab(
                  active: !_useQrMode,
                  icon: Icons.smartphone_rounded,
                  label: 'Nomor HP & OTP',
                  onTap: () {
                    _stopQrTimer();
                    setState(() {
                      _useQrMode = false;
                      _qrUrl = null;
                      _errorMsg = null;
                    });
                  },
                ),
              ),
              Expanded(
                child: _methodTab(
                  active: _useQrMode,
                  icon: Icons.qr_code_rounded,
                  label: 'Scan QR (HP Lain)',
                  onTap: () {
                    setState(() {
                      _useQrMode = true;
                      _errorMsg = null;
                    });
                  },
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),

        _buildWhitelistBox(_whitelistCtrl),
        const SizedBox(height: 16),

        if (!_useQrMode) ...[
          const Text(
            'Nomor Telepon Telegram',
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w600,
              color: Colors.white,
            ),
          ),
          const SizedBox(height: 6),
          TextField(
            controller: _phoneCtrl,
            keyboardType: TextInputType.phone,
            style: const TextStyle(fontSize: 14, color: Colors.white),
            decoration: _inputDeco('+6281234567890 atau 081234567890'),
          ),
          const SizedBox(height: 6),
          const Text(
            'Kode OTP dikirim ke chat resmi Telegram. Jika OTP terhambat, pakai tab Scan QR.',
            style: TextStyle(fontSize: 11, color: Colors.white38),
          ),
          const SizedBox(height: 14),
          ElevatedButton.icon(
            style: ElevatedButton.styleFrom(
              backgroundColor: kTgBlue,
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(vertical: 14),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
            onPressed: _isBusy ? null : _handleSendOtp,
            icon: _isBusy
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: Colors.white,
                    ),
                  )
                : const Icon(Icons.arrow_forward_rounded, size: 18),
            label: Text(
              _isBusy ? 'Mengirim OTP...' : 'Lanjut & Kirim OTP',
              style: const TextStyle(fontWeight: FontWeight.w600),
            ),
          ),
        ] else ...[
          if (_qrUrl == null) ...[
            ElevatedButton.icon(
              style: ElevatedButton.styleFrom(
                backgroundColor: kTgBlue,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 14),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
              onPressed: _isBusy ? null : _handleStartQr,
              icon: const Icon(Icons.qr_code_2_rounded, size: 19),
              label: Text(
                _isBusy ? 'Membuat QR Code...' : 'Buat QR Code Telegram',
                style: const TextStyle(fontWeight: FontWeight.w600),
              ),
            ),
            const SizedBox(height: 8),
            const Text(
              'Scan dari perangkat lain (Telegram HP -> Settings -> Devices -> Link Desktop Device).',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 11, color: Colors.white38),
            ),
          ] else ...[
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: kBgColor,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: kBorderColor),
              ),
              child: Column(
                children: [
                  Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: QrImageView(
                      data: _qrUrl!,
                      version: QrVersions.auto,
                      size: 190,
                    ),
                  ),
                  const SizedBox(height: 12),
                  const Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      SizedBox(
                        width: 14,
                        height: 14,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: kTgBlue,
                        ),
                      ),
                      SizedBox(width: 8),
                      Text(
                        'Menunggu scan dari Telegram HP...',
                        style: TextStyle(
                          fontSize: 12,
                          color: kTgBlue,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      Expanded(
                        child: OutlinedButton(
                          style: OutlinedButton.styleFrom(
                            side: const BorderSide(color: kBorderColor),
                            foregroundColor: Colors.white70,
                          ),
                          onPressed: _handleStartQr,
                          child: const Text('Buat Ulang'),
                        ),
                      ),
                      const SizedBox(width: 8),
                      OutlinedButton(
                        style: OutlinedButton.styleFrom(
                          side: const BorderSide(color: kBorderColor),
                          foregroundColor: Colors.white54,
                        ),
                        onPressed: () {
                          _stopQrTimer();
                          setState(() => _qrUrl = null);
                        },
                        child: const Text('Batal'),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ],

        const SizedBox(height: 14),
        // Developer mode accordion
        Container(
          decoration: BoxDecoration(
            color: kBgColor,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: kBorderColor),
          ),
          child: ExpansionTile(
            tilePadding: const EdgeInsets.symmetric(horizontal: 12),
            childrenPadding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
            collapsedIconColor: Colors.white38,
            iconColor: kTgBlue,
            shape: const Border(),
            title: const Text(
              'Mode Developer: API ID / Server Sendiri (Opsional)',
              style: TextStyle(fontSize: 11.5, color: Colors.white60),
            ),
            children: [
              const Text(
                'Pengguna biasa biarkan kosong (otomatis memakai server & API bawaan).',
                style: TextStyle(fontSize: 11, color: Colors.white38),
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _apiIdCtrl,
                      keyboardType: TextInputType.number,
                      style: const TextStyle(fontSize: 12, color: Colors.white),
                      decoration: _inputDeco('API ID'),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: TextField(
                      controller: _apiHashCtrl,
                      style: const TextStyle(fontSize: 12, color: Colors.white),
                      decoration: _inputDeco('API Hash'),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              TextField(
                controller: _serverUrlCtrl,
                style: const TextStyle(fontSize: 12, color: Colors.white),
                decoration: _inputDeco('Server API URL'),
              ),
            ],
          ),
        ),

        const SizedBox(height: 14),
        const Divider(color: kBorderColor, height: 1),
        const SizedBox(height: 12),
        const Wrap(
          spacing: 12,
          runSpacing: 6,
          children: [
            _TrustChip(icon: Icons.verified_user_outlined, color: kEmerald, label: 'Kontak HP aman'),
            _TrustChip(icon: Icons.lock_outline, color: Colors.white54, label: 'Zero-storage'),
            _TrustChip(icon: Icons.logout, color: Colors.white54, label: 'Auto-logout'),
            _TrustChip(icon: Icons.person_outline, color: Colors.white54, label: 'Blokir Bot opsional'),
          ],
        ),
      ],
    );
  }

  Widget _methodTab({
    required bool active,
    required IconData icon,
    required String label,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 9),
        decoration: BoxDecoration(
          color: active ? const Color(0xFF27272A) : Colors.transparent,
          borderRadius: BorderRadius.circular(9),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, size: 15, color: active ? kTgBlue : Colors.white54),
            const SizedBox(width: 6),
            Text(
              label,
              style: TextStyle(
                fontSize: 12,
                fontWeight: active ? FontWeight.w600 : FontWeight.w500,
                color: active ? Colors.white : Colors.white54,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildStep2() {
    return _cardContainer(
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            const Text(
              'Verifikasi Kode & Filter',
              style: TextStyle(
                fontSize: 17,
                fontWeight: FontWeight.w700,
                color: Colors.white,
              ),
            ),
            TextButton(
              onPressed: () => _resetToStep1(callLogout: true),
              child: const Text('Kembali', style: TextStyle(fontSize: 12)),
            ),
          ],
        ),
        Text(
          'Dikirim ke $_displayPhone ($_deliveryInfo)',
          style: const TextStyle(fontSize: 12, color: kTgBlue),
        ),
        const SizedBox(height: 16),

        if (!_hideOtpFor2FA) ...[
          const Text(
            'Kode OTP Telegram (5 Digit)',
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w600,
              color: Colors.white,
            ),
          ),
          const SizedBox(height: 6),
          TextField(
            controller: _otpCtrl,
            keyboardType: TextInputType.number,
            textAlign: TextAlign.center,
            style: const TextStyle(
              fontSize: 22,
              fontFamily: 'monospace',
              letterSpacing: 8,
              color: Colors.white,
            ),
            decoration: _inputDeco('•••••'),
          ),
          const SizedBox(height: 14),
        ],

        if (_requires2FA) ...[
          Container(
            padding: const EdgeInsets.all(12),
            margin: const EdgeInsets.only(bottom: 14),
            decoration: BoxDecoration(
              color: const Color(0xFF281D08),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: Colors.amber.withAlpha(110)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Masukkan Password Verifikasi 2 Langkah (2FA)',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: Colors.amberAccent,
                  ),
                ),
                const SizedBox(height: 8),
                TextField(
                  controller: _twoFaCtrl,
                  obscureText: true,
                  style: const TextStyle(fontSize: 13, color: Colors.white),
                  decoration: _inputDeco('Password 2FA Telegram Anda'),
                ),
              ],
            ),
          ),
        ],

        _buildWhitelistBox(_whitelistCtrl),
        const SizedBox(height: 16),

        ElevatedButton.icon(
          style: ElevatedButton.styleFrom(
            backgroundColor: kTgBlue,
            foregroundColor: Colors.white,
            padding: const EdgeInsets.symmetric(vertical: 14),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
            ),
          ),
          onPressed: _isBusy ? null : _handleVerifyScan,
          icon: _isBusy
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: Colors.white,
                  ),
                )
              : const Icon(Icons.manage_search_rounded, size: 18),
          label: Text(
            _isBusy ? 'Memindai Akun...' : 'Verifikasi & Pindai Akun',
            style: const TextStyle(fontWeight: FontWeight.w600),
          ),
        ),
      ],
    );
  }

  List<DialogTarget> _filteredTargets() {
    final query = _searchCtrl.text.trim().toLowerCase();
    return _targets.where((t) {
      if (_categoryFilter != 'ALL' && t.type != _categoryFilter) return false;
      if (query.isEmpty) return true;
      return t.name.toLowerCase().contains(query) ||
          t.username.toLowerCase().contains(query) ||
          t.type.toLowerCase().contains(query);
    }).toList();
  }

  Widget _buildCategoryFilterBar() {
    final Map<String, int> counts = {'ALL': _targets.length};
    for (final t in _targets) {
      counts[t.type] = (counts[t.type] ?? 0) + 1;
    }
    const order = [
      ('ALL', 'Semua'),
      ('Grup', 'Grup'),
      ('Saluran', 'Saluran'),
      ('Bot', 'Bot'),
      ('Akun Terhapus', 'Akun Terhapus'),
    ];
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        children: [
          for (final entry in order)
            if (entry.$1 == 'ALL' || (counts[entry.$1] ?? 0) > 0) ...[
              ChoiceChip(
                label: Text('${entry.$2} (${counts[entry.$1] ?? 0})'),
                selected: _categoryFilter == entry.$1,
                onSelected: (_) => setState(() => _categoryFilter = entry.$1),
                selectedColor: kTgBlue.withAlpha(45),
                backgroundColor: kBgColor,
                side: BorderSide(
                  color: _categoryFilter == entry.$1
                      ? kTgBlue.withAlpha(140)
                      : kBorderColor,
                ),
                labelStyle: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                  color: _categoryFilter == entry.$1
                      ? const Color(0xFF38BDF8)
                      : Colors.white60,
                ),
              ),
              const SizedBox(width: 6),
            ],
        ],
      ),
    );
  }

  Widget _buildStep3() {
    final filteredTargets = _filteredTargets();

    return _cardContainer(
      children: [
        Row(
          children: [
            const CircleAvatar(radius: 4, backgroundColor: kEmerald),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                'Akun: ${_user?.displayName ?? "-"}',
                style: const TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w700,
                  color: Colors.white,
                ),
                overflow: TextOverflow.ellipsis,
              ),
            ),
            TextButton.icon(
              onPressed: () => _resetToStep1(callLogout: true),
              icon: const Icon(Icons.logout, size: 15, color: Colors.redAccent),
              label: const Text(
                'Batal',
                style: TextStyle(fontSize: 12, color: Colors.redAccent),
              ),
            ),
          ],
        ),
        const SizedBox(height: 10),

        // Metric row
        Row(
          children: [
            Expanded(
              child: _metricCard(
                'Target Ditemukan',
                '${_targets.length}',
                Colors.redAccent,
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: _metricCard(
                'Dilindungi (Aman)',
                '${_protectedItems.length}',
                kEmerald,
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),

        // Tabs Target vs Dilindungi
        Row(
          children: [
            ChoiceChip(
              label: const Text('Target Dihapus'),
              selected: !_showProtectedTab,
              onSelected: (_) => setState(() => _showProtectedTab = false),
              selectedColor: const Color(0xFF27272A),
              backgroundColor: kBgColor,
              labelStyle: TextStyle(
                fontSize: 12,
                color: !_showProtectedTab ? Colors.white : Colors.white54,
              ),
            ),
            const SizedBox(width: 8),
            ChoiceChip(
              label: const Text('Daftar Dilindungi'),
              selected: _showProtectedTab,
              onSelected: (_) => setState(() => _showProtectedTab = true),
              selectedColor: const Color(0xFF27272A),
              backgroundColor: kBgColor,
              labelStyle: TextStyle(
                fontSize: 12,
                color: _showProtectedTab ? Colors.white : Colors.white54,
              ),
            ),
          ],
        ),
        const SizedBox(height: 10),

        if (!_showProtectedTab) ...[
          _buildCategoryFilterBar(),
          const SizedBox(height: 8),
          TextField(
            controller: _searchCtrl,
            onChanged: (_) => setState(() {}),
            style: const TextStyle(fontSize: 13, color: Colors.white),
            decoration: _inputDeco('Cari nama grup, saluran, atau bot...'),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              TextButton(
                onPressed: () => setState(() {
                  _selectedIds.addAll(filteredTargets.map((e) => e.id));
                }),
                child: const Text('Pilih Semua', style: TextStyle(fontSize: 12)),
              ),
              TextButton(
                onPressed: () => setState(() {
                  _selectedIds.removeAll(filteredTargets.map((e) => e.id));
                }),
                child: const Text(
                  'Hapus Centang',
                  style: TextStyle(fontSize: 12, color: Colors.white54),
                ),
              ),
            ],
          ),
          ConstrainedBox(
            constraints: const BoxConstraints(maxHeight: 280),
            child: filteredTargets.isEmpty
                ? const Padding(
                    padding: EdgeInsets.symmetric(vertical: 28),
                    child: Text(
                      'Tidak ada item target spam yang ditemukan.',
                      textAlign: TextAlign.center,
                      style: TextStyle(fontSize: 12, color: Colors.white54),
                    ),
                  )
                : ListView.builder(
                    shrinkWrap: true,
                    itemCount: filteredTargets.length,
                    itemBuilder: (_, idx) {
                      final t = filteredTargets[idx];
                      final checked = _selectedIds.contains(t.id);
                      return Container(
                        margin: const EdgeInsets.only(bottom: 6),
                        decoration: BoxDecoration(
                          color: kBgColor,
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(color: kBorderColor),
                        ),
                        child: CheckboxListTile(
                          value: checked,
                          activeColor: kDanger,
                          dense: true,
                          controlAffinity: ListTileControlAffinity.leading,
                          onChanged: (val) {
                            setState(() {
                              if (val == true) {
                                _selectedIds.add(t.id);
                              } else {
                                _selectedIds.remove(t.id);
                              }
                            });
                          },
                          title: Text(
                            t.name,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              fontSize: 13,
                              color: Colors.white,
                            ),
                          ),
                          subtitle: Text(
                            t.username.isNotEmpty
                                ? '@${t.username} • ${t.type}'
                                : t.type,
                            style: const TextStyle(
                              fontSize: 11,
                              color: Colors.white54,
                            ),
                          ),
                        ),
                      );
                    },
                  ),
          ),
        ] else ...[
          ConstrainedBox(
            constraints: const BoxConstraints(maxHeight: 320),
            child: _protectedItems.isEmpty
                ? const Padding(
                    padding: EdgeInsets.symmetric(vertical: 24),
                    child: Text(
                      'Tidak ada item dilindungi.',
                      textAlign: TextAlign.center,
                      style: TextStyle(fontSize: 12, color: Colors.white54),
                    ),
                  )
                : ListView.builder(
                    shrinkWrap: true,
                    itemCount: _protectedItems.length,
                    itemBuilder: (_, idx) {
                      final p = _protectedItems[idx];
                      return Container(
                        margin: const EdgeInsets.only(bottom: 6),
                        padding: const EdgeInsets.symmetric(
                          horizontal: 12,
                          vertical: 10,
                        ),
                        decoration: BoxDecoration(
                          color: kBgColor,
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(color: kBorderColor),
                        ),
                        child: Row(
                          children: [
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    p.name,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: const TextStyle(
                                      fontSize: 13,
                                      color: Colors.white,
                                    ),
                                  ),
                                  Text(
                                    p.username.isNotEmpty ? '@${p.username}' : 'Aman',
                                    style: const TextStyle(
                                      fontSize: 11,
                                      color: Colors.white38,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 8,
                                vertical: 3,
                              ),
                              decoration: BoxDecoration(
                                color: kEmerald.withAlpha(35),
                                borderRadius: BorderRadius.circular(6),
                              ),
                              child: Text(
                                p.reason,
                                style: const TextStyle(
                                  fontSize: 10,
                                  color: kEmerald,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ),
                          ],
                        ),
                      );
                    },
                  ),
          ),
        ],

        const SizedBox(height: 12),
        CheckboxListTile(
          value: _blockBots,
          onChanged: (v) => setState(() => _blockBots = v ?? false),
          activeColor: kDanger,
          contentPadding: EdgeInsets.zero,
          controlAffinity: ListTileControlAffinity.leading,
          title: const Text(
            'Sekalian Blokir Bot terpilih permanen',
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w600,
              color: Colors.white,
            ),
          ),
          subtitle: const Text(
            'Hanya memblokir tipe Bot; Grup & Saluran tetap keluar bersih.',
            style: TextStyle(fontSize: 11, color: Colors.white54),
          ),
        ),
        CheckboxListTile(
          value: _autoLogout,
          onChanged: (v) => setState(() => _autoLogout = v ?? true),
          activeColor: kTgBlue,
          contentPadding: EdgeInsets.zero,
          controlAffinity: ListTileControlAffinity.leading,
          title: const Text(
            'Otomatis logout sesi CleanGram dari Telegram Devices setelah selesai',
            style: TextStyle(fontSize: 12, color: Colors.white70),
          ),
        ),
        const SizedBox(height: 8),
        ElevatedButton.icon(
          style: ElevatedButton.styleFrom(
            backgroundColor: kDanger,
            foregroundColor: Colors.white,
            padding: const EdgeInsets.symmetric(vertical: 14),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
            ),
          ),
          onPressed: _selectedIds.isEmpty ? null : _confirmAndClean,
          icon: const Icon(Icons.delete_sweep_rounded, size: 19),
          label: Text(
            _selectedIds.isEmpty
                ? 'Pilih Minimal 1 Target'
                : 'Bersihkan ${_selectedIds.length} Target Terpilih',
            style: const TextStyle(fontWeight: FontWeight.w700),
          ),
        ),
      ],
    );
  }

  Widget _metricCard(String label, String value, Color accent) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: kBgColor,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: kBorderColor),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(fontSize: 11, color: Colors.white54),
          ),
          const SizedBox(height: 4),
          Text(
            value,
            style: TextStyle(
              fontSize: 22,
              fontFamily: 'monospace',
              fontWeight: FontWeight.w700,
              color: accent,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildStep4() {
    final pct = (_progress * 100).round();
    return _cardContainer(
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              _cleaningDone ? 'Pembersihan Selesai' : 'Membersihkan Akun...',
              style: const TextStyle(
                fontSize: 17,
                fontWeight: FontWeight.w700,
                color: Colors.white,
              ),
            ),
            Text(
              '$pct%',
              style: const TextStyle(
                fontSize: 16,
                fontFamily: 'monospace',
                fontWeight: FontWeight.w700,
                color: kTgBlue,
              ),
            ),
          ],
        ),
        const SizedBox(height: 10),
        ClipRRect(
          borderRadius: BorderRadius.circular(8),
          child: LinearProgressIndicator(
            value: _progress,
            minHeight: 8,
            backgroundColor: kBgColor,
            color: _cleaningDone ? kEmerald : kTgBlue,
          ),
        ),
        const SizedBox(height: 14),
        Container(
          height: 240,
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: kBgColor,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: kBorderColor),
          ),
          child: ListView.builder(
            controller: _logScrollCtrl,
            itemCount: _logs.length,
            itemBuilder: (_, i) => Padding(
              padding: const EdgeInsets.only(bottom: 3),
              child: Text(
                _logs[i].text,
                style: TextStyle(
                  fontSize: 11,
                  fontFamily: 'monospace',
                  color: _logs[i].color,
                ),
              ),
            ),
          ),
        ),
        if (_cleaningDone) ...[
          const SizedBox(height: 14),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: kEmerald.withAlpha(28),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: kEmerald.withAlpha(90)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  '✓ Pembersihan Selesai & Sesi Di-Logout Permanen',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    color: kEmerald,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  'Berhasil keluar & hapus riwayat $_totalSuccess item${_totalFailed > 0 ? " ($_totalFailed dilewati)" : ""}.',
                  style: const TextStyle(fontSize: 12, color: Colors.white70),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: kTgBlue,
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(vertical: 13),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
            onPressed: () => _resetToStep1(callLogout: false),
            child: const Text(
              'Selesai',
              style: TextStyle(fontWeight: FontWeight.w600),
            ),
          ),
        ],
      ],
    );
  }

  Widget _buildFooter() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 16),
      decoration: const BoxDecoration(
        border: Border(top: BorderSide(color: kBorderColor)),
      ),
      child: GestureDetector(
        onTap: () => _openExternalUrl('https://github.com/BenedichtusRW'),
        child: RichText(
          textAlign: TextAlign.center,
          text: const TextSpan(
            style: TextStyle(fontSize: 11, color: Colors.white38),
            children: [
              TextSpan(text: 'CleanGram Open Source • Built by '),
              TextSpan(
                text: 'ben_dev',
                style: TextStyle(
                  fontFamily: 'monospace',
                  color: Colors.white70,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _TrustChip extends StatelessWidget {
  final IconData icon;
  final Color color;
  final String label;

  const _TrustChip({
    required this.icon,
    required this.color,
    required this.label,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 13, color: color),
        const SizedBox(width: 4),
        Text(label, style: const TextStyle(fontSize: 11, color: Colors.white54)),
      ],
    );
  }
}
