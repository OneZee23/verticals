// The pictures of a report, made small enough to live in a document (docs/design/bug-reports.md). A document holds 512 KiB
// (core/docs.py MAX_DOC_BODY_BYTES), and one screenshot from a Retina screen is a few times that. So each picture is drawn
// smaller and saved as a JPEG, as small as the room needs: all of them share what the document has left after the words
// and the logs, a picture that comes out small leaves its room to the ones after it, and when there are many each gets less
// (a clear half-screen for one or two, a thumbnail for dozens). A picture that cannot fit even as a thumbnail is left out of
// the report, and the answer says how many.

/** Characters of data URL all the pictures may take together: 512 KiB less the words, the version and the logs (about 20 kB). */
export const PICTURES_BUDGET = 400_000
/** Longest side and JPEG quality, from the clearest to the smallest. A picture is never drawn larger than it is. */
const STEPS: ReadonlyArray<readonly [number, number]> = [
  [1600, 0.82], [1280, 0.76], [1024, 0.7], [800, 0.64], [640, 0.58], [480, 0.52], [360, 0.46], [240, 0.4],
]
/** The fewest characters of data URL one pixel of a screenshot comes to, even at the lowest quality: a step whose pixels
 *  could not fit are not tried. */
const LEAST_PER_PIXEL = 0.12

export interface EncodedPictures {
  /** The data URLs of the pictures that fit, in the order they were dropped. */
  sources: string[]
  /** How many did not. */
  left: number
}

async function draw(bitmap: ImageBitmap, side: number, quality: number, allowed: number): Promise<string | null> {
  const scale = Math.min(1, side / Math.max(bitmap.width, bitmap.height))
  const width = Math.max(1, Math.round(bitmap.width * scale))
  const height = Math.max(1, Math.round(bitmap.height * scale))
  if (width * height * LEAST_PER_PIXEL > allowed) return null
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const context = canvas.getContext('2d')
  if (!context) return null
  // A picture with see-through parts is drawn on white: a JPEG has none.
  context.fillStyle = '#fff'
  context.fillRect(0, 0, width, height)
  context.drawImage(bitmap, 0, 0, width, height)
  const url = canvas.toDataURL('image/jpeg', quality)
  return url.length <= allowed ? url : null
}

async function encode(file: File, allowed: number): Promise<string | null> {
  let bitmap: ImageBitmap
  try {
    bitmap = await createImageBitmap(file)
  } catch {
    return null
  }
  try {
    for (const [side, quality] of STEPS) {
      const url = await draw(bitmap, side, quality, allowed)
      if (url) return url
    }
    return null
  } finally {
    bitmap.close()
  }
}

export async function encodePictures(files: File[], budget = PICTURES_BUDGET): Promise<EncodedPictures> {
  const sources: string[] = []
  let left = 0
  let remaining = budget
  for (const [index, file] of files.entries()) {
    const url = await encode(file, Math.floor(remaining / (files.length - index)))
    if (url) {
      sources.push(url)
      remaining -= url.length
    } else {
      left += 1
    }
  }
  return { sources, left }
}
