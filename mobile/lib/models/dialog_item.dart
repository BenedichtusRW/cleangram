class DialogTarget {
  final int id;
  final String name;
  final String username;
  final String type;

  const DialogTarget({
    required this.id,
    required this.name,
    required this.username,
    required this.type,
  });

  factory DialogTarget.fromJson(Map<String, dynamic> json) {
    return DialogTarget(
      id: (json['id'] as num).toInt(),
      name: (json['name'] as String?) ?? '[Tanpa Nama]',
      username: (json['username'] as String?) ?? '',
      type: (json['type'] as String?) ?? 'Target',
    );
  }
}

class ProtectedItem {
  final int id;
  final String name;
  final String username;
  final String reason;

  const ProtectedItem({
    required this.id,
    required this.name,
    required this.username,
    required this.reason,
  });

  factory ProtectedItem.fromJson(Map<String, dynamic> json) {
    return ProtectedItem(
      id: (json['id'] as num).toInt(),
      name: (json['name'] as String?) ?? '[Tanpa Nama]',
      username: (json['username'] as String?) ?? '',
      reason: (json['reason'] as String?) ?? 'Aman',
    );
  }
}

class UserSummary {
  final String firstName;
  final String lastName;
  final String username;

  const UserSummary({
    required this.firstName,
    required this.lastName,
    required this.username,
  });

  String get displayName {
    final full = '$firstName $lastName'.trim();
    return username.isNotEmpty ? '$full (@$username)' : full;
  }

  factory UserSummary.fromJson(Map<String, dynamic> json) {
    return UserSummary(
      firstName: (json['first_name'] as String?) ?? 'Pengguna',
      lastName: (json['last_name'] as String?) ?? '',
      username: (json['username'] as String?) ?? '',
    );
  }
}

class ScanResult {
  final String status;
  final String flowToken;
  final UserSummary? user;
  final List<DialogTarget> targets;
  final List<ProtectedItem> protectedItems;

  const ScanResult({
    required this.status,
    required this.flowToken,
    this.user,
    this.targets = const [],
    this.protectedItems = const [],
  });

  factory ScanResult.fromJson(Map<String, dynamic> json) {
    final status = (json['status'] as String?) ?? '';
    final flowToken = (json['flow_token'] as String?) ?? '';
    if (status == '2fa_required') {
      return ScanResult(status: status, flowToken: flowToken);
    }

    final rawTargets = (json['targets'] as List<dynamic>?) ?? [];
    final rawProtected = (json['protected'] as List<dynamic>?) ?? [];
    return ScanResult(
      status: status,
      flowToken: flowToken,
      user: json['user'] != null
          ? UserSummary.fromJson(json['user'] as Map<String, dynamic>)
          : null,
      targets: rawTargets
          .map((e) => DialogTarget.fromJson(e as Map<String, dynamic>))
          .toList(),
      protectedItems: rawProtected
          .map((e) => ProtectedItem.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}

class BatchItemResult {
  final int id;
  final String name;
  final String type;
  final String status;
  final String message;

  const BatchItemResult({
    required this.id,
    required this.name,
    required this.type,
    required this.status,
    required this.message,
  });

  factory BatchItemResult.fromJson(Map<String, dynamic> json) {
    return BatchItemResult(
      id: (json['id'] as num).toInt(),
      name: (json['name'] as String?) ?? '',
      type: (json['type'] as String?) ?? '-',
      status: (json['status'] as String?) ?? 'error',
      message: (json['message'] as String?) ?? '',
    );
  }
}

class BatchCleanResult {
  final List<BatchItemResult> results;
  final int sukses;
  final int gagal;
  final int floodwaitSeconds;
  final bool loggedOut;

  const BatchCleanResult({
    required this.results,
    required this.sukses,
    required this.gagal,
    required this.floodwaitSeconds,
    required this.loggedOut,
  });

  factory BatchCleanResult.fromJson(Map<String, dynamic> json) {
    final raw = (json['results'] as List<dynamic>?) ?? [];
    return BatchCleanResult(
      results: raw
          .map((e) => BatchItemResult.fromJson(e as Map<String, dynamic>))
          .toList(),
      sukses: (json['sukses'] as num?)?.toInt() ?? 0,
      gagal: (json['gagal'] as num?)?.toInt() ?? 0,
      floodwaitSeconds: (json['floodwait_seconds'] as num?)?.toInt() ?? 0,
      loggedOut: (json['logged_out'] as bool?) ?? false,
    );
  }
}
