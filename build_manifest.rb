#!/usr/bin/env ruby
# frozen_string_literal: true

# build_manifest.rb — VellumFE asset-repository manifest generator (PROTOTYPE)
#
# Walks a `vellum-assets` monorepo and emits one Jinx-compatible
# manifest.json per category folder. Multi-file assets (skins, layouts,
# icon sets) are packed into reproducible `.vellumpack` zips; single-file
# assets (game data) are listed as-is.
#
# This is a CI-only script: it runs in GitHub Actions, never on a user
# machine and never inside VellumFE. Its ONE hard requirement is digest
# parity with Jinx and the VellumFE client:
#
#     md5 = Digest::SHA1.base64digest(delivered_bytes)
#
# (The field is historically named "md5"; the value is base64 SHA1. The
#  Rust client computes the identical digest and compares.)
#
# Usage:
#   ruby build_manifest.rb --root . [--base-url https://nisugi.github.io/vellum-assets]
#
# Layout it expects:
#   <root>/skins/<name>/{meta.toml, preview.png, skin.toml, ...}
#   <root>/icons/<name>/{meta.toml, ...}
#   <root>/layouts/<name>/{meta.toml, ...}      # or a prebuilt <name>.vellumpack + meta.toml
#   <root>/data/<file>.xml                       # single-file, no packing
#
# Output (one per category, served at that category's Pages sub-path):
#   <root>/skins/manifest.json
#   <root>/icons/manifest.json
#   <root>/layouts/manifest.json
#   <root>/data/manifest.json
#
# NOTE: prototype. TOML parsing uses a tiny built-in reader so the script
# has zero gem dependencies; swap for the `toml-rb` gem if richer meta is
# needed. Not wired to any repo yet — run against a local test tree.

require 'json'
require 'digest'
require 'base64'
require 'zlib'
require 'find'
require 'optparse'

# --- Category configuration -------------------------------------------------
#
# `pack: true`  -> the asset is a directory zipped into <name>.vellumpack
# `pack: false` -> each file in the folder is its own single-file asset
# `pool:`       -> shared-image-pool folder the client installs into
#                  (global/images/<pool>/); emitted as vellum.pool so NEW
#                  categories install with no client release. Directory-safe
#                  names only ([a-z0-9_-], <=32 chars) or the client ignores it.
CATEGORIES = {
  # Skins are folders (skin.toml + art) -> zipped to <name>.vellumpack.
  'skins'   => { type: 'skin',    pack: true,  ext: '.vellumpack' },
  # Icon maps are individual PNG files -> listed as-is (each one installable).
  'icons'   => { type: 'iconmap', pack: false, ext: nil, pool: 'icons' },
  # Layouts are prebuilt .vellumpack files (from .uiexport) -> listed as-is.
  'layouts' => { type: 'layout',  pack: false, ext: nil },
  # Paper dolls are individual PNG files -> listed as-is.
  'dolls'   => { type: 'doll',    pack: false, ext: nil, pool: 'dolls' },
  # Status glyph pool: individual PNGs named <set>_<glyph>.png.
  'statusicons' => { type: 'statusicon', pack: false, ext: nil, pool: 'statusicons', set_piece: true },
  # Hand icons (left/right/spell) for the hands widget: <set>_<hand>.png.
  'hands'   => { type: 'hand',    pack: false, ext: nil, pool: 'hands', set_piece: true },
  # Compass element pool: individual PNGs named <set>_<role>.png.
  'compass' => { type: 'compass', pack: false, ext: nil, pool: 'compass', set_piece: true },
  # Window frames (nine-slice): single PNGs, slice/scale in sidecar toml.
  'frames'  => { type: 'frame',   pack: false, ext: nil, pool: 'frames' },
  # Window background textures: opaque single PNGs.
  'backgrounds' => { type: 'background', pack: false, ext: nil, pool: 'backgrounds' },
  # Game data files -> listed as-is.
  'data'    => { type: 'data',    pack: false, ext: nil }
}.freeze

# Files never included in a bundle or listed as assets.
IGNORED = ['.DS_Store', 'Thumbs.db', 'manifest.json', '.gitkeep'].freeze

# --- Jinx-parity digest -----------------------------------------------------
# The single most important line in this file: byte-for-byte what Jinx and
# the VellumFE Rust client compute. Do not "optimize" this.
def digest_b64(bytes)
  Digest::SHA1.base64digest(bytes)
end

# --- Git commit time --------------------------------------------------------
# Real last-commit epoch so the client's "modified N ago" is truthful.
# Requires the checkout to have full history (actions/checkout fetch-depth: 0).
# Falls back to file mtime outside a git tree (local testing).
def last_commit(path)
  # Redirect both streams so a non-git tree stays quiet on every platform
  # (Windows `git` writes "cannot find the path" to stderr).
  out = IO.popen(['git', 'log', '-1', '--format=%ct', '--', path], err: File::NULL, &:read).to_s.strip
  return out.to_i unless out.empty?

  File.mtime(path).to_i
rescue StandardError
  File.mtime(path).to_i
end

# --- Reproducible zip (no gems) --------------------------------------------
# Deterministic .vellumpack: entries sorted, timestamps zeroed, so the same
# source tree always produces the same bytes -> the same digest. A
# non-deterministic zip would flip the digest on every CI run and show every
# asset as "update available."
#
# Minimal STORE-only (no compression) ZIP writer. Deflate can be added later;
# STORE keeps the prototype dependency-free and fully deterministic. The
# VellumFE client reads it with the `zip` crate regardless.
class ReproZip
  def initialize
    @entries = []
  end

  # name: forward-slash path inside the zip; data: String bytes
  def add(name, data)
    @entries << [name.tr('\\', '/'), data.b]
  end

  def bytes
    # Sort for determinism.
    sorted = @entries.sort_by(&:first)
    out = +''.b
    central = +''.b
    offset = 0

    sorted.each do |name, data|
      crc = Zlib.crc32(data)
      name_b = name.b
      # Local file header (STORE, method 0, dostime 0).
      local = [
        0x04034b50, 20, 0, 0, 0, 0, # sig, ver, flags, method, time, date
        crc, data.bytesize, data.bytesize,
        name_b.bytesize, 0
      ].pack('VvvvvvVVVvv') + name_b
      out << local << data

      central << [
        0x02014b50, 20, 20, 0, 0, 0, 0,
        crc, data.bytesize, data.bytesize,
        name_b.bytesize, 0, 0, 0, 0, 0,
        offset
      ].pack('VvvvvvvVVVvvvvvVV') + name_b

      offset += local.bytesize + data.bytesize
    end

    cd_size = central.bytesize
    cd_off = out.bytesize
    eocd = [
      0x06054b50, 0, 0, sorted.size, sorted.size,
      cd_size, cd_off, 0
    ].pack('VvvvvVVv')

    out << central << eocd
    out
  end
end

# --- Tiny TOML reader (flat keys only) --------------------------------------
# Enough for meta.toml: strings, integers, and string arrays at the top level.
# Swap for toml-rb if nested tables are ever needed.
def read_meta_toml(path)
  return {} unless File.file?(path)

  meta = {}
  File.read(path).each_line do |line|
    line = line.strip
    next if line.empty? || line.start_with?('#', '[')

    key, _, raw = line.partition('=')
    key = key.strip
    raw = raw.strip
    next if key.empty? || raw.empty?

    meta[key] =
      if raw.start_with?('[') && raw.end_with?(']')
        raw[1..-2].split(',').map { |s| s.strip.delete('"\'') }.reject(&:empty?)
      elsif raw.start_with?('"') || raw.start_with?("'")
        raw[1..-2]
      elsif raw.match?(/\A-?\d+\z/)
        raw.to_i
      elsif raw.match?(/\A-?\d+\.\d+\z/)
        raw.to_f
      else
        raw
      end
  end
  meta
end

# --- vellum:{} block from meta.toml -----------------------------------------
def vellum_block(meta, category_type, pool = nil)
  block = {}
  block['title']       = meta['title']       if meta['title']
  block['author']      = meta['author']      if meta['author']
  block['description'] = meta['description']  if meta['description']
  block['version']     = meta['version']     if meta['version']
  block['tags']        = Array(meta['tags']) if meta['tags']
  block['preview']     = meta['preview']     if meta['preview']
  # Rendering metadata for single-file assets that need it (sheets, frames).
  block['cell']        = meta['cell']        if meta['cell']
  block['slice']       = meta['slice']       if meta['slice']
  block['scale']       = meta['scale']       if meta['scale']
  block['category']    = category_type       # inferred, always present
  # Shared-image-pool folder: the client installs the file into
  # global/images/<pool>/ from this tag alone, so a new category here needs
  # no client release.
  block['pool']        = pool                if pool
  block.empty? ? nil : block
end

# --- Pack a directory into a .vellumpack ------------------------------------
def pack_directory(dir)
  zip = ReproZip.new
  files = []
  Find.find(dir) do |p|
    next unless File.file?(p)

    base = File.basename(p)
    next if IGNORED.include?(base)

    files << p
  end
  files.sort.each do |p|
    rel = p.sub(/\A#{Regexp.escape(dir)}\/?/, '')
    zip.add(rel, File.binread(p))
  end
  zip.bytes
end

# --- Build one category's manifest ------------------------------------------
def build_category(root, category, config, base_url)
  cat_dir = File.join(root, category)
  return nil unless Dir.exist?(cat_dir)

  available = []

  if config[:pack]
    # Each immediate subdirectory is one asset.
    Dir.children(cat_dir).sort.each do |name|
      asset_dir = File.join(cat_dir, name)
      next unless File.directory?(asset_dir)

      meta = read_meta_toml(File.join(asset_dir, 'meta.toml'))
      bytes = pack_directory(asset_dir)
      file_name = "#{name}#{config[:ext]}"

      # `file` is relative to THIS category's base URL (each category is a
      # separately-seeded repo, e.g. .../vellum-assets/skins), so no category
      # prefix — that would double it (.../skins/skins/x).
      entry = {
        'file'        => "/#{file_name}",
        'type'        => config[:type],
        'md5'         => digest_b64(bytes),
        'last_commit' => last_commit(asset_dir)
      }
      vb = vellum_block(meta, config[:type])
      entry['vellum'] = vb if vb
      available << entry

      # The generated bundle is written beside the source so Pages serves it.
      File.binwrite(File.join(cat_dir, file_name), bytes)
    end
  else
    # Single-file assets: list each file as-is. A sidecar <name>.toml (written
    # by the submission pipeline) supplies gallery/render metadata.
    Dir.children(cat_dir).sort.each do |name|
      next if IGNORED.include?(name) || name.end_with?('.json', '.toml')

      path = File.join(cat_dir, name)
      next unless File.file?(path)

      meta = read_meta_toml(File.join(cat_dir, "#{File.basename(name, '.*')}.toml"))

      # Relative to this category's base URL — no category prefix (see above).
      entry = {
        'file'        => "/#{name}",
        'type'        => config[:type],
        'md5'         => digest_b64(File.binread(path)),
        'last_commit' => last_commit(path)
      }
      vb = vellum_block(meta, config[:type], config[:pool])
      # Pool assets following the <set>_<piece> convention publish their
      # set name so the client groups members without parsing filenames.
      # Pieces never contain underscores, set names may — so the set is
      # everything before the LAST underscore. Directory-safe values only;
      # anything else is omitted rather than published broken.
      if config[:set_piece] && vb
        set = File.basename(name, '.*').rpartition('_').first
        vb['set'] = set if set.match?(/\A[a-z0-9_-]+\z/)
      end
      entry['vellum'] = vb if vb
      available << entry
    end
  end

  manifest = { 'available' => available }
  out_path = File.join(cat_dir, 'manifest.json')
  File.write(out_path, JSON.pretty_generate(manifest) + "\n")
  [out_path, available.size]
end

# --- Discovery index --------------------------------------------------------
# repos.json at the monorepo root lists every category present as its own
# Jinx repo. The VellumFE client merges it (add-only) on top of its
# compiled-in seeds, so a new category folder here reaches every client
# without a release on their side.
def write_repos_index(root, base_url)
  repos = CATEGORIES.keys.select { |c| Dir.exist?(File.join(root, c)) }.sort.map do |c|
    { 'name' => "vellum-#{c}", 'url' => "#{base_url}/#{c}" }
  end
  path = File.join(root, 'repos.json')
  File.write(path, JSON.pretty_generate({ 'repos' => repos }) + "\n")
  [path, repos.size]
end

# --- CLI --------------------------------------------------------------------
def main
  options = { root: '.', base_url: 'https://nisugi.github.io/vellum-assets' }
  OptionParser.new do |o|
    o.banner = 'Usage: ruby build_manifest.rb [--root DIR] [--base-url URL]'
    o.on('--root DIR', 'monorepo root (default: .)') { |v| options[:root] = v }
    o.on('--base-url URL', 'Pages base url (repos.json entries)') { |v| options[:base_url] = v }
  end.parse!

  root = File.expand_path(options[:root])
  total = 0
  CATEGORIES.each do |category, config|
    result = build_category(root, category, config, options[:base_url])
    next unless result

    out_path, count = result
    puts "wrote #{out_path} (#{count} asset#{count == 1 ? '' : 's'})"
    total += count
  end
  index_path, repo_count = write_repos_index(root, options[:base_url])
  puts "wrote #{index_path} (#{repo_count} repo#{repo_count == 1 ? '' : 's'})"
  puts "done: #{total} asset#{total == 1 ? '' : 's'} across #{CATEGORIES.size} categories"
end

main if $PROGRAM_NAME == __FILE__
